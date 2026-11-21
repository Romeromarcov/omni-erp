"""
Tests de integración, RLS, seguridad y paridad MCP para persistencia de consumo
y costos LLM por tenant (Plan 05 P2-3).

Cubre:
  1. ``calcular_costo_estimado_usd`` en ``Decimal`` (tarifas default, prefijos,
     redondeo ``ROUND_HALF_UP`` y overrides/validación por env ``LLM_PRICING_JSON``).
  2. Persistencia automática desde ``LLMGateway.generate()`` y ``stream()`` vía
     hook conectado en ``AgentesConfig.ready()`` (idempotente).
  3. Diseño fail-safe del hook: UUID inválido, empresa inexistente, fallo de BD
     dentro de ``@transaction.atomic`` sin envenenar la transacción padre y
     rollback pendiente manejado limpiamente.
  4. PostgreSQL RLS en ``agentes_consumo_llm`` (``FORCE ROW LEVEL SECURITY``,
     ``null_visible=True``, aislamiento cross-tenant y ``WITH CHECK``).
  5. API REST ``/api/agentes/consumo-llm/`` y ``/resumen/``: filtros por
     ``empresa_id``, ``modelo``, ``uso``, ``fecha_desde``/``fecha_hasta``,
     validaciones ``400``/``403``, IDOR ``404``, inmutabilidad ``405``,
     exclusión estricta de filas globales ``id_empresa=None``, admin solo lectura.
  6. Paridad MCP: ``agentes_resumen_consumo_llm`` (``agentes:read``),
     ``CapabilityToken``, RLS fail-closed, validación UUID/fechas/NUL y error saneado.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid

from django.apps import apps as django_apps
from django.contrib import admin as django_admin
from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError
from django.test import RequestFactory, override_settings
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.agentes.models import ConsumoLLM
from apps.agentes.services import persistir_consumo_llm, registrar_hook_consumo_llm
from apps.core import llm_gateway, rls
from apps.core.llm_gateway import LLMGateway, USO_AGENTE, USO_ANALISIS, USO_CHAT, calcular_costo_estimado_usd
from apps.core.models import CapabilityToken, Empresa

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

URL_CONSUMO = "/api/agentes/consumo-llm/"
URL_RESUMEN = "/api/agentes/consumo-llm/resumen/"


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


def _respuesta_mock(texto="ok", tokens_in=100, tokens_out=50):
    return SimpleNamespace(
        content=[SimpleNamespace(text=texto)],
        usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out),
        stop_reason="end_turn",
    )


class _StreamManagerMock:
    def __init__(self, tokens_in=200, tokens_out=100):
        self._final = _respuesta_mock("stream-ok", tokens_in=tokens_in, tokens_out=tokens_out)
        self._stream = SimpleNamespace(
            text_stream=iter(("hola ", "mundo")),
            get_final_message=lambda: self._final,
        )

    def __enter__(self):
        return self._stream

    def __exit__(self, *_exc):
        return False


# ── 1. Cálculo exacto Decimal y LLM_PRICING_JSON ──────────────────────────────


class TestCalculoCostoDecimal:
    def test_tarifas_default_y_redondeo_decimal(self, monkeypatch):
        monkeypatch.delenv("LLM_PRICING_JSON", raising=False)
        modelo_agente = llm_gateway.modelo_configurado(USO_AGENTE)  # 1.00 / 5.00 por 1M
        modelo_chat = llm_gateway.modelo_configurado(USO_CHAT)  # 3.00 / 15.00 por 1M
        modelo_analisis = llm_gateway.modelo_configurado(USO_ANALISIS)  # 5.00 / 25.00 por 1M

        # 1,000 in * 1.00/1M + 500 out * 5.00/1M = 0.001000 + 0.002500 = 0.003500
        costo_agente = calcular_costo_estimado_usd(modelo_agente, 1000, 500)
        assert isinstance(costo_agente, Decimal)
        assert costo_agente == Decimal("0.003500")

        # 2,000 in * 3.00/1M + 1,000 out * 15.00/1M = 0.006 + 0.015 = 0.021000
        assert calcular_costo_estimado_usd(modelo_chat, 2000, 1000) == Decimal("0.021000")

        # 1,000 in * 5.00/1M + 1,000 out * 25.00/1M = 0.030000
        assert calcular_costo_estimado_usd(modelo_analisis, 1000, 1000) == Decimal("0.030000")

        # Match por prefijo de familia (snapshot nuevo), case-insensitive, y redondeo HALF_UP
        # 1 token input * 3.00/1M = 0.000003; 1 token output * 15.00/1M = 0.000015 -> 0.000018
        assert calcular_costo_estimado_usd(f"{modelo_chat}-20260901", 1, 1) == Decimal("0.000018")
        assert calcular_costo_estimado_usd(modelo_chat.upper(), 1_000_000, 0) == Decimal("3.000000")
        # 0.5 microUSD -> 0.0000005 -> ROUND_HALF_UP -> 0.000001 (con tarifa 1.00 USD/1M y 0.5 token? Con 500 tokens @ 0.001? Probamos 1 token a 1.50/1M -> 0.0000015 -> 0.000002)
        monkeypatch.setenv("LLM_PRICING_JSON", json.dumps({"mi-modelo": {"input": "1.50", "output": "2.00"}}))
        assert calcular_costo_estimado_usd("mi-modelo", 1, 0) == Decimal("0.000002")

        # Modelo desconocido usa tarifa fallback default (3.00 / 15.00)
        assert calcular_costo_estimado_usd("proveedor-externo-x", 1_000_000, 0) == Decimal("3.000000")

        # Tokens negativos o inválidos se acotan a 0
        assert calcular_costo_estimado_usd("mi-modelo", -10, "abc") == Decimal("0.000000")  # type: ignore[arg-type]

    def test_llm_pricing_json_tolera_valores_invalidos(self, monkeypatch):
        modelo_chat = llm_gateway.modelo_configurado(USO_CHAT)

        monkeypatch.setenv("LLM_PRICING_JSON", "{no-es-json")
        assert calcular_costo_estimado_usd(modelo_chat, 1_000_000, 0) == Decimal("3.000000")

        monkeypatch.setenv("LLM_PRICING_JSON", '["no-es-objeto"]')
        assert calcular_costo_estimado_usd(modelo_chat, 1_000_000, 0) == Decimal("3.000000")

        monkeypatch.setenv(
            "LLM_PRICING_JSON",
            json.dumps(
                {
                    " ": {"input": "1", "output": "1"},
                    "malo-neg": {"input": "-1", "output": "2"},
                    "malo-str": {"input": "no-num", "output": "2"},
                    "malo-bool": {"input": True, "output": "2"},
                    "bueno": {"input": "10.00", "output": "20.00"},
                }
            ),
        )
        assert calcular_costo_estimado_usd("bueno", 1000, 1000) == Decimal("0.030000")
        assert calcular_costo_estimado_usd("malo-neg", 1_000_000, 0) == Decimal("3.000000")


# ── 2. Persistencia automática desde generate() y stream() + idempotencia ─────


class TestPersistenciaAutomaticaHook:
    def test_ready_idempotente_y_generate_stream_persisten_consumo(self, empresa_a, monkeypatch):
        monkeypatch.delenv("LLM_PRICING_JSON", raising=False)
        cfg = django_apps.get_app_config("agentes")
        # Idempotente: si ya hay un hook temporal, ready(force=False) no lo pisa;
        # registrar_hook_consumo_llm() sí reconecta el persistente.
        sentinel = lambda _evt: None  # noqa: E731
        monkeypatch.setattr(llm_gateway, "registrar_consumo_hook", sentinel)
        cfg.ready()
        assert llm_gateway.registrar_consumo_hook is sentinel
        registrar_hook_consumo_llm()
        assert llm_gateway.registrar_consumo_hook is persistir_consumo_llm

        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_mock("ok", tokens_in=10_000, tokens_out=2_000)
        cliente.messages.stream.return_value = _StreamManagerMock(tokens_in=5_000, tokens_out=1_000)
        gw = LLMGateway(client=cliente, breaker=llm_gateway._CircuitBreaker())

        r = gw.generate(prompt="clasifica", uso=USO_AGENTE, empresa=empresa_a)
        assert r.text == "ok"

        with gw.stream(messages=[{"role": "user", "content": "hola"}], uso=USO_CHAT, empresa=empresa_a) as s:
            assert "".join(s.text_stream) == "hola mundo"

        registros = list(ConsumoLLM.objects.filter(id_empresa=empresa_a).order_by("creado_en", "id_consumo"))
        assert len(registros) == 2

        c_gen, c_str = registros
        assert c_gen.proveedor == "anthropic"
        assert c_gen.uso == USO_AGENTE
        assert c_gen.modelo == llm_gateway.modelo_configurado(USO_AGENTE)
        assert c_gen.tokens_entrada == 10_000
        assert c_gen.tokens_salida == 2_000
        # 10k * 1/1M (0.01) + 2k * 5/1M (0.01) = 0.020000
        assert c_gen.costo_estimado_usd == Decimal("0.020000")
        assert c_gen.latencia_ms >= 0
        assert str(empresa_a.pk) in str(c_gen)

        assert c_str.uso == USO_CHAT
        assert c_str.modelo == llm_gateway.modelo_configurado(USO_CHAT)
        assert c_str.tokens_entrada == 5_000
        assert c_str.tokens_salida == 1_000
        # 5k * 3/1M (0.015) + 1k * 15/1M (0.015) = 0.030000
        assert c_str.costo_estimado_usd == Decimal("0.030000")

    def test_llamada_sin_empresa_persiste_global_null(self):
        registrar_hook_consumo_llm()
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_mock("global", tokens_in=100, tokens_out=0)
        gw = LLMGateway(client=cliente, breaker=llm_gateway._CircuitBreaker())

        gw.generate(prompt="sistema", uso=USO_AGENTE, empresa=None)
        c = ConsumoLLM.objects.filter(id_empresa__isnull=True).latest("creado_en")
        assert c.tokens_entrada == 100
        assert "global" in str(c)


# ── 3. Diseño fail-safe y preservación de @transaction.atomic ─────────────────


class TestFailSafeHook:
    def test_entradas_invalidas_y_empresa_inexistente_no_fallan(self):
        assert persistir_consumo_llm("no-dict") is None  # type: ignore[arg-type]
        assert persistir_consumo_llm({"empresa_id": "no-es-uuid", "modelo": "m"}) is None
        assert (
            persistir_consumo_llm(
                {
                    "empresa_id": str(uuid.uuid4()),
                    "proveedor": "anthropic",
                    "uso": "agente",
                    "modelo": "m",
                    "tokens_entrada": True,
                    "tokens_salida": "invalido",
                    "latencia_ms": -5,
                }
            )
            is None
        )

    @pytest.mark.django_db(transaction=True)
    def test_fallo_db_en_hook_no_rompe_llm_ni_envenena_atomic_externo(self, empresa_a):
        registrar_hook_consumo_llm()
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_mock("resiliente", tokens_in=50, tokens_out=25)
        gw = LLMGateway(client=cliente, breaker=llm_gateway._CircuitBreaker())

        with patch.object(
            ConsumoLLM.objects,
            "create",
            side_effect=IntegrityError("fallo simulado en persistencia"),
        ):
            with transaction.atomic():
                # Operación previa en la transacción externa
                assert Empresa.objects.filter(pk=empresa_a.pk).exists()
                r = gw.generate(prompt="hola", uso=USO_AGENTE, empresa=empresa_a)
                assert r.text == "resiliente"
                # La transacción externa sigue sana (no quedó en needs_rollback=True)
                assert Empresa.objects.filter(pk=empresa_a.pk).count() == 1
                assert ConsumoLLM.objects.filter(id_empresa=empresa_a).count() == 0

    def test_needs_rollback_pendiente_omite_escritura_limpiamente(self, empresa_a):
        with patch.object(connection, "needs_rollback", True):
            res = persistir_consumo_llm(
                {
                    "proveedor": "anthropic",
                    "uso": "agente",
                    "modelo": "m",
                    "empresa_id": str(empresa_a.pk),
                    "tokens_entrada": 10,
                    "tokens_salida": 5,
                    "latencia_ms": 1,
                }
            )
        assert res is None


# ── 4. PostgreSQL RLS en agentes_consumo_llm ──────────────────────────────────


@pytest.mark.tenant
class TestRlsConsumoLLM:
    @override_settings(RLS_ENABLED=True)
    def test_rls_force_aisla_tenants_y_bloquea_with_check(self, rls_test_role, empresa_a, empresa_b):
        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            with rls.rls_bypass():
                c_a = ConsumoLLM.objects.create(
                    id_empresa=empresa_a,
                    proveedor="anthropic",
                    uso="agente",
                    modelo="m-a",
                    tokens_entrada=100,
                    tokens_salida=50,
                    costo_estimado_usd=Decimal("0.000350"),
                )
                c_b = ConsumoLLM.objects.create(
                    id_empresa=empresa_b,
                    proveedor="anthropic",
                    uso="chat",
                    modelo="m-b",
                    tokens_entrada=200,
                    tokens_salida=100,
                    costo_estimado_usd=Decimal("0.002100"),
                )
                c_global = ConsumoLLM.objects.create(
                    id_empresa=None,
                    proveedor="anthropic",
                    uso="agente",
                    modelo="m-global",
                    tokens_entrada=10,
                    tokens_salida=5,
                )

            rls.apply_system_default()
            # Sin contexto: ninguna fila de tenant es visible (solo NULL si existiera, nunca c_a ni c_b)
            assert ConsumoLLM.objects.filter(pk__in=[c_a.pk, c_b.pk]).count() == 0

            with rls.rls_tenant_context([empresa_a.pk]):
                visibles_a = set(ConsumoLLM.objects.values_list("pk", flat=True))
                assert c_a.pk in visibles_a
                assert c_b.pk not in visibles_a
                assert c_global.pk in visibles_a  # null_visible=True a nivel PG
                with pytest.raises((IntegrityError, ProgrammingError)):
                    with transaction.atomic():
                        ConsumoLLM.objects.create(
                            id_empresa=empresa_b,
                            proveedor="anthropic",
                            uso="agente",
                            modelo="intruso",
                        )

            with rls.rls_tenant_context([empresa_b.pk]):
                visibles_b = set(ConsumoLLM.objects.values_list("pk", flat=True))
                assert c_b.pk in visibles_b
                assert c_a.pk not in visibles_b
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")


# ── 5. API REST ReadOnly + Resumen + Filtros + Seguridad + Admin ──────────────


@pytest.mark.tenant
class TestConsumoLLMApiYAdmin:
    @pytest.fixture
    def subsidiaria_a(self, empresa_a, moneda_usd):
        return Empresa.objects.create(
            nombre_legal="Subsidiaria Consumo S.A.",
            identificador_fiscal="J-22222222-2",
            empresa_matriz=empresa_a,
            id_moneda_base=moneda_usd,
        )

    def test_aislamiento_exclusivo_sin_globales_filtros_resumen_y_solo_lectura(
        self, client_a, client_b, empresa_a, empresa_b, subsidiaria_a
    ):
        hoy = timezone.localdate()
        ayer = hoy - timedelta(days=1)

        c_a1 = ConsumoLLM.objects.create(
            id_empresa=empresa_a,
            proveedor="anthropic",
            uso="agente",
            modelo="m-haiku",
            tokens_entrada=1000,
            tokens_salida=500,
            costo_estimado_usd=Decimal("0.003500"),
            latencia_ms=100,
        )
        c_a2 = ConsumoLLM.objects.create(
            id_empresa=empresa_a,
            proveedor="anthropic",
            uso="chat",
            modelo="m-sonnet",
            tokens_entrada=2000,
            tokens_salida=1000,
            costo_estimado_usd=Decimal("0.021000"),
            latencia_ms=200,
        )
        # Ayer en subsidiaria
        c_sub = ConsumoLLM.objects.create(
            id_empresa=subsidiaria_a,
            proveedor="anthropic",
            uso="analisis",
            modelo="m-opus",
            tokens_entrada=100,
            tokens_salida=50,
            costo_estimado_usd=Decimal("0.001750"),
            latencia_ms=300,
        )
        ConsumoLLM.objects.filter(pk=c_sub.pk).update(creado_en=timezone.now() - timedelta(days=1))

        # Empresa B y fila global (id_empresa=None) NUNCA deben aparecer
        c_b = ConsumoLLM.objects.create(
            id_empresa=empresa_b,
            proveedor="anthropic",
            uso="chat",
            modelo="m-sonnet",
            tokens_entrada=9999,
            tokens_salida=9999,
            costo_estimado_usd=Decimal("9.999999"),
            latencia_ms=999,
        )
        c_global = ConsumoLLM.objects.create(
            id_empresa=None,
            proveedor="anthropic",
            uso="agente",
            modelo="m-global",
            tokens_entrada=8888,
            tokens_salida=8888,
            costo_estimado_usd=Decimal("8.888888"),
            latencia_ms=888,
        )

        # Listado completo para A: incluye matriz + subsidiaria, excluye B y global
        r_list = client_a.get(URL_CONSUMO)
        assert r_list.status_code == 200
        ids = {row["id_consumo"] for row in r_list.json()["results"]}
        assert ids == {str(c_a1.pk), str(c_a2.pk), str(c_sub.pk)}
        assert str(c_b.pk) not in ids
        assert str(c_global.pk) not in ids

        # Resumen total para A (sin globales ni B)
        r_res = client_a.get(URL_RESUMEN)
        assert r_res.status_code == 200
        body = r_res.json()
        assert body["llamadas"] == 3
        assert body["tokens_entrada_total"] == 3100
        assert body["tokens_salida_total"] == 1550
        assert body["costo_total_usd"] == "0.026250"
        assert body["latencia_promedio_ms"] == 200
        assert len(body["por_modelo"]) == 3
        assert len(body["por_uso"]) == 3
        assert {m["modelo"] for m in body["por_modelo"]} == {"m-haiku", "m-sonnet", "m-opus"}

        # Filtro por ?empresa_id= (matriz y subsidiaria OK; ajena 403; inválido 400)
        r_emp = client_a.get(f"{URL_RESUMEN}?empresa_id={empresa_a.pk}")
        assert r_emp.status_code == 200
        assert r_emp.json()["llamadas"] == 2
        assert r_emp.json()["costo_total_usd"] == "0.024500"

        r_sub = client_a.get(f"{URL_CONSUMO}?empresa_id={subsidiaria_a.pk}")
        assert r_sub.status_code == 200
        assert [row["id_consumo"] for row in r_sub.json()["results"]] == [str(c_sub.pk)]

        assert client_a.get(f"{URL_CONSUMO}?empresa_id={empresa_b.pk}").status_code == 403
        assert client_a.get(f"{URL_RESUMEN}?empresa_id={empresa_b.pk}").status_code == 403

        # Filtros por ?modelo=, ?uso=, ?fecha_desde=, ?fecha_hasta=, ?search=, ?ordering=
        r_mod = client_a.get(f"{URL_RESUMEN}?modelo=m-sonnet&uso=chat")
        assert r_mod.status_code == 200
        assert r_mod.json()["llamadas"] == 1
        assert r_mod.json()["costo_total_usd"] == "0.021000"

        r_fecha = client_a.get(f"{URL_RESUMEN}?fecha_desde={ayer.isoformat()}&fecha_hasta={ayer.isoformat()}")
        assert r_fecha.status_code == 200
        assert r_fecha.json()["llamadas"] == 1
        assert r_fecha.json()["por_modelo"][0]["modelo"] == "m-opus"

        r_hoy = client_a.get(f"{URL_CONSUMO}?fecha_desde={hoy.isoformat()}&fecha_hasta=&ordering=-costo_estimado_usd")
        assert r_hoy.status_code == 200
        assert [row["id_consumo"] for row in r_hoy.json()["results"]] == [str(c_a2.pk), str(c_a1.pk)]

        r_search = client_a.get(f"{URL_CONSUMO}?search=m-haiku")
        assert [row["id_consumo"] for row in r_search.json()["results"]] == [str(c_a1.pk)]

        # Retrieve detalle propio vs IDOR ajeno / global -> 404
        assert client_a.get(f"{URL_CONSUMO}{c_a1.pk}/").status_code == 200
        assert client_a.get(f"{URL_CONSUMO}{c_b.pk}/").status_code == 404
        assert client_a.get(f"{URL_CONSUMO}{c_global.pk}/").status_code == 404
        assert client_b.get(f"{URL_CONSUMO}{c_a1.pk}/").status_code == 404

        # Inmutabilidad: POST / PUT / PATCH / DELETE -> 405
        assert client_a.post(URL_CONSUMO, {}, format="json").status_code == 405
        assert client_a.put(f"{URL_CONSUMO}{c_a1.pk}/", {}, format="json").status_code == 405
        assert client_a.patch(f"{URL_CONSUMO}{c_a1.pk}/", {}, format="json").status_code == 405
        assert client_a.delete(f"{URL_CONSUMO}{c_a1.pk}/").status_code == 405

    def test_resumen_vacio_y_validaciones_400_y_401(self, client_a):
        assert APIClient().get(URL_CONSUMO).status_code == 401
        assert APIClient().get(URL_RESUMEN).status_code == 401

        r_vacio = client_a.get(URL_RESUMEN)
        assert r_vacio.status_code == 200
        assert r_vacio.json() == {
            "llamadas": 0,
            "tokens_entrada_total": 0,
            "tokens_salida_total": 0,
            "costo_total_usd": "0.000000",
            "latencia_promedio_ms": 0,
            "por_modelo": [],
            "por_uso": [],
        }

        # UUIDs inválidos -> 400
        assert client_a.get(f"{URL_CONSUMO}000000000000000000000000000000000000/").status_code == 400
        assert client_a.get(f"{URL_CONSUMO}?empresa_id=bad-uuid").status_code == 400
        assert client_a.get(f"{URL_RESUMEN}?empresa_id=bad-uuid").status_code == 400

        # Fechas inválidas o invertidas -> 400
        assert client_a.get(f"{URL_CONSUMO}?fecha_desde=2026-13-01").status_code == 400
        assert client_a.get(f"{URL_CONSUMO}?fecha_desde=no-fecha").status_code == 400
        assert client_a.get(f"{URL_RESUMEN}?fecha_hasta=2026/11/21").status_code == 400
        assert client_a.get(f"{URL_RESUMEN}?fecha_desde=2026-11-21&fecha_hasta=2026-11-01").status_code == 400

        # NUL bytes -> 400
        assert client_a.get(f"{URL_CONSUMO}?modelo=x%00y").status_code == 400
        assert client_a.get(f"{URL_CONSUMO}?uso=chat%00").status_code == 400
        assert client_a.get(f"{URL_CONSUMO}?fecha_desde=2026-11-01%00").status_code == 400
        assert client_a.get(f"{URL_CONSUMO}?search=a%00b").status_code == 400

    def test_admin_consumo_llm_solo_lectura(self, user_a):
        model_admin = django_admin.site._registry[ConsumoLLM]
        req = RequestFactory().get("/admin/")
        req.user = user_a
        assert model_admin.has_add_permission(req) is False
        assert model_admin.has_change_permission(req) is False
        assert model_admin.has_delete_permission(req) is False


# ── 6. Paridad MCP (agentes_resumen_consumo_llm) ──────────────────────────────


@pytest.mark.tenant
class TestMcpConsumoLLMParity:
    @pytest.fixture
    def tokens(self, empresa_a, empresa_b):
        tok_a_ro = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Consumo A RO",
            scopes=["agentes:read"],
        )
        tok_a_wo = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Consumo A WO",
            scopes=["agentes:write"],
        )
        tok_b = CapabilityToken.objects.create(
            empresa=empresa_b,
            nombre="Consumo B RO",
            scopes=["agentes:read"],
        )
        return tok_a_ro, tok_a_wo, tok_b

    def test_mcp_autodiscovery_y_fastmcp(self):
        from apps.agentes.mcp import MCP_TOOLS
        from apps.core import mcp_server

        nombres = {t["name"] for t in MCP_TOOLS}
        assert "agentes_resumen_consumo_llm" in nombres
        assert "agentes_resumen_consumo_llm" in mcp_server._DISCOVERED_TOOLS
        registered = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert "agentes_resumen_consumo_llm" in registered

    @pytest.mark.django_db(transaction=True)
    @override_settings(RLS_ENABLED=True)
    def test_mcp_resumen_consumo_aislamiento_filtros_y_errores(self, rls_test_role, tokens, empresa_a, empresa_b):
        from apps.agentes import mcp as agentes_mcp

        tok_a_ro, tok_a_wo, tok_b = tokens
        hoy = timezone.localdate()

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            with rls.rls_bypass():
                ConsumoLLM.objects.create(
                    id_empresa=empresa_a,
                    proveedor="anthropic",
                    uso="agente",
                    modelo="m-a",
                    tokens_entrada=400,
                    tokens_salida=200,
                    costo_estimado_usd=Decimal("0.001400"),
                    latencia_ms=120,
                )
                ConsumoLLM.objects.create(
                    id_empresa=empresa_b,
                    proveedor="anthropic",
                    uso="chat",
                    modelo="m-b",
                    tokens_entrada=5000,
                    tokens_salida=5000,
                    costo_estimado_usd=Decimal("5.000000"),
                    latencia_ms=500,
                )
                ConsumoLLM.objects.create(
                    id_empresa=None,
                    proveedor="anthropic",
                    uso="agente",
                    modelo="m-global",
                    tokens_entrada=777,
                    tokens_salida=777,
                    costo_estimado_usd=Decimal("7.777777"),
                    latencia_ms=777,
                )

            rls.apply_system_default()

            # Consulta válida bajo RLS fail-closed -> restaura ("off", "") al salir
            res_a = agentes_mcp.agentes_resumen_consumo_llm(
                str(tok_a_ro.token),
                str(empresa_a.pk),
                fecha_desde=hoy.isoformat(),
                fecha_hasta=hoy.isoformat(),
                modelo="m-a",
                uso="agente",
            )
            assert res_a["llamadas"] == 1
            assert res_a["tokens_entrada_total"] == 400
            assert res_a["tokens_salida_total"] == 200
            assert res_a["costo_total_usd"] == "0.001400"
            assert res_a["latencia_promedio_ms"] == 120
            assert rls._get_current_context() == ("off", "")

            # Scope insuficiente (solo write) -> PermissionError
            with pytest.raises(PermissionError):
                agentes_mcp.agentes_resumen_consumo_llm(str(tok_a_wo.token), str(empresa_a.pk))

            # Cross-tenant -> PermissionError o aislado solo a B
            with pytest.raises(PermissionError):
                agentes_mcp.agentes_resumen_consumo_llm(str(tok_a_ro.token), str(empresa_b.pk))

            res_b = agentes_mcp.agentes_resumen_consumo_llm(str(tok_b.token), str(empresa_b.pk), fecha_desde="   ")
            assert res_b["llamadas"] == 1
            assert res_b["costo_total_usd"] == "5.000000"

            # Validación de fechas y NUL bytes -> dict con "error"
            assert "error" in agentes_mcp.agentes_resumen_consumo_llm(
                str(tok_a_ro.token), str(empresa_a.pk), fecha_desde="bad-date"
            )
            assert "error" in agentes_mcp.agentes_resumen_consumo_llm(
                str(tok_a_ro.token), str(empresa_a.pk), fecha_desde="2026-99-99"
            )
            assert "error" in agentes_mcp.agentes_resumen_consumo_llm(
                str(tok_a_ro.token),
                str(empresa_a.pk),
                fecha_desde="2026-11-21",
                fecha_hasta="2026-11-01",
            )
            assert "error" in agentes_mcp.agentes_resumen_consumo_llm(
                str(tok_a_ro.token), str(empresa_a.pk), modelo="x\x00y"
            )
            assert "error" in agentes_mcp.agentes_resumen_consumo_llm(
                str(tok_a_ro.token), str(empresa_a.pk), fecha_desde="2026-11-01\x00"
            )

            # Error inesperado de BD -> saneado (R-CODE-8)
            with patch(
                "apps.agentes.models.ConsumoLLM.objects.filter",
                side_effect=RuntimeError("SELECT * FROM agentes_consumo_llm detalle_interno_oculto"),
            ):
                err = agentes_mcp.agentes_resumen_consumo_llm(str(tok_a_ro.token), str(empresa_a.pk))
            assert "error" in err
            assert "SELECT" not in err["error"]
            assert "detalle_interno_oculto" not in err["error"]
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")
