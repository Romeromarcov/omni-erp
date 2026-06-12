"""
Backfill de cobertura — apps/cxc/api/{fraccionamiento,cobranza,agente}.py
(plan "Cero Dudas"). Prefijo: /api/cobranza/ (apps/cxc/api/router.py).

Cubre:

- fraccionamiento.py: feature flag (403 lista/creación sin flag), creación de
  lote con inicialización de cantidad_actual, soft delete, reserva de stock en
  ventas pendientes (M-BUG-8, 400 al sobrevender), confirmar (descuento de
  stock Decimal exacto, lote agotado, 400 re-confirmar), resumen KPIs.
- cobranza.py: plantillas CRUD + soft delete, gestiones (perform_create con
  score y empresa inyectada, aislamiento), agenda, prioridades,
  preview-plantilla (400 sin plantilla + render feliz).
- agente.py: 401 sin token, 429 al superar rate limit, streaming SSE feliz
  con agente mockeado (sin llamar a Anthropic).

Dinero como Decimal con aserciones exactas.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.configuracion_motor.models import ParametroSistema
from apps.cxc.models import (
    GestionCobranza,
    LoteFraccionado,
    PlantillaCobranza,
    VentaFraccionada,
)

pytestmark = pytest.mark.django_db

BASE = "/api/cobranza/"


def _results(resp):
    data = resp.json()
    return data.get("results", data) if isinstance(data, dict) else data


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


@pytest.fixture
def flag_fraccionamiento_a(empresa_a):
    """Habilita cxc.fraccionamiento.enabled para la Empresa A."""
    return ParametroSistema.objects.create(
        id_empresa=empresa_a,
        nombre_parametro="Fraccionamiento habilitado",
        codigo_parametro="cxc.fraccionamiento.enabled",
        valor_parametro="true",
        tipo_dato="BOOLEANO",
        activo=True,
    )


@pytest.fixture
def lote_a(empresa_a):
    return LoteFraccionado.objects.create(
        empresa=empresa_a,
        producto_id="PROD-001",
        producto_nombre="Queso artesanal",
        cantidad_inicial=Decimal("10.0000"),
        cantidad_actual=Decimal("10.0000"),
        unidad_base="kg",
        unidad_venta="g",
        factor_conversion=Decimal("1000.000000"),
        precio_venta_unit=Decimal("0.0500"),
        estado="activo",
    )


@pytest.fixture
def venta_pendiente_a(empresa_a, lote_a):
    return VentaFraccionada.objects.create(
        empresa=empresa_a,
        lote=lote_a,
        cliente_id="CLI-001",
        cliente_nombre="Cliente Uno",
        cantidad=Decimal("4.0000"),
        precio_unit=Decimal("0.0500"),
        monto_total=Decimal("0.2000"),
        estado="pendiente",
    )


@pytest.fixture
def plantilla_a(empresa_a):
    return PlantillaCobranza.objects.create(
        empresa=empresa_a,
        nombre="Recordatorio WhatsApp",
        canal="whatsapp",
        asunto="Pago pendiente",
        cuerpo="Hola {cliente}, su orden {orden} por {monto} vence el {vencimiento} ({dias_vencida} días).",
        activa=True,
    )


@pytest.fixture
def gestion_a(empresa_a, user_a, plantilla_a):
    return GestionCobranza.objects.create(
        empresa=empresa_a,
        cliente_id="CLI-001",
        cliente_nombre="Cliente Uno",
        orden_ref="ORD-77",
        canal="whatsapp",
        resultado="promesa_pago",
        plantilla=plantilla_a,
        fecha_gestion=datetime.date(2026, 6, 8),
        proxima_accion=datetime.date(2026, 6, 10),
        gestionado_por=user_a,
    )


class TestAutenticacionRequerida:
    @pytest.mark.parametrize(
        "route", ["gestiones", "plantillas", "lotes", "ventas-fraccionadas"]
    )
    def test_401_sin_token(self, route):
        resp = APIClient().get(f"{BASE}{route}/")
        assert resp.status_code == 401

    def test_agente_401_sin_token(self):
        resp = APIClient().post(f"{BASE}agente/", {})
        assert resp.status_code == 401


class TestLoteFraccionado:
    def test_list_sin_flag_403(self, client_a, empresa_a):
        resp = client_a.get(f"{BASE}lotes/")
        assert resp.status_code == 403
        assert "no habilitado" in resp.json()["detail"]

    def test_list_con_flag_200(self, client_a, flag_fraccionamiento_a, lote_a):
        resp = client_a.get(f"{BASE}lotes/")
        assert resp.status_code == 200
        ids = [r["id"] for r in _results(resp)]
        assert str(lote_a.id) in ids

    def test_create_sin_flag_403(self, client_a, empresa_a):
        resp = client_a.post(
            f"{BASE}lotes/",
            {
                "producto_id": "P-X",
                "producto_nombre": "Producto X",
                "cantidad_inicial": "5.0000",
                "cantidad_actual": "0",
                "unidad_base": "kg",
                "unidad_venta": "g",
                "factor_conversion": "1000",
                "precio_venta_unit": "0.10",
            },
        )
        assert resp.status_code == 403
        assert LoteFraccionado.objects.count() == 0

    def test_create_inicializa_cantidad_actual(self, client_a, flag_fraccionamiento_a,
                                                empresa_a):
        resp = client_a.post(
            f"{BASE}lotes/",
            {
                "producto_id": "P-NEW",
                "producto_nombre": "Harina",
                "cantidad_inicial": "20.0000",
                "cantidad_actual": "0",
                "unidad_base": "saco",
                "unidad_venta": "kg",
                "factor_conversion": "45",
                "precio_venta_unit": "1.2500",
            },
        )
        assert resp.status_code == 201
        lote = LoteFraccionado.objects.get(producto_id="P-NEW")
        assert lote.empresa_id == empresa_a.pk
        assert lote.cantidad_actual == Decimal("20.0000")

    def test_b_no_ve_lotes_de_a(self, client_b, empresa_b, lote_a):
        ParametroSistema.objects.create(
            id_empresa=empresa_b,
            nombre_parametro="Flag B",
            codigo_parametro="cxc.fraccionamiento.enabled",
            valor_parametro="true",
            tipo_dato="BOOLEANO",
            activo=True,
        )
        resp = client_b.get(f"{BASE}lotes/")
        assert resp.status_code == 200
        assert str(lote_a.id) not in [r["id"] for r in _results(resp)]

    def test_retrieve_lote_cross_tenant_404(self, client_b, lote_a):
        resp = client_b.get(f"{BASE}lotes/{lote_a.id}/")
        assert resp.status_code == 404

    def test_destroy_es_soft_delete(self, client_a, flag_fraccionamiento_a, lote_a):
        resp = client_a.delete(f"{BASE}lotes/{lote_a.id}/")
        assert resp.status_code == 204
        lote_a.refresh_from_db()
        assert lote_a.deleted_at is not None
        # Soft-deleted: ya no aparece en la lista pero sigue en BD
        resp2 = client_a.get(f"{BASE}lotes/")
        assert str(lote_a.id) not in [r["id"] for r in _results(resp2)]


class TestVentaFraccionada:
    def _payload(self, lote, cantidad="2.0000"):
        return {
            "lote": str(lote.id),
            "cliente_id": "CLI-002",
            "cliente_nombre": "Cliente Dos",
            "cantidad": cantidad,
            "precio_unit": "0.0500",
            "monto_total": "0.1000",
        }

    def test_create_sin_flag_403(self, client_a, lote_a):
        resp = client_a.post(f"{BASE}ventas-fraccionadas/", self._payload(lote_a))
        assert resp.status_code == 403

    def test_create_ok_reserva_stock(self, client_a, flag_fraccionamiento_a, lote_a,
                                      empresa_a):
        resp = client_a.post(f"{BASE}ventas-fraccionadas/", self._payload(lote_a))
        assert resp.status_code == 201
        venta = VentaFraccionada.objects.get(cliente_id="CLI-002")
        assert venta.estado == "pendiente"
        assert venta.empresa_id == empresa_a.pk
        # Crear no descuenta stock todavía (solo reserva)
        lote_a.refresh_from_db()
        assert lote_a.cantidad_actual == Decimal("10.0000")

    def test_create_sobreventa_400(self, client_a, flag_fraccionamiento_a, lote_a,
                                    venta_pendiente_a):
        # Pendiente reserva 4; pedir 7 sobrevende el lote de 10 (M-BUG-8)
        resp = client_a.post(
            f"{BASE}ventas-fraccionadas/", self._payload(lote_a, cantidad="7.0000")
        )
        assert resp.status_code == 400
        assert "Stock insuficiente para reservar" in str(resp.json())
        assert VentaFraccionada.objects.filter(lote=lote_a).count() == 1

    def test_confirmar_descuenta_stock(self, client_a, lote_a, venta_pendiente_a):
        resp = client_a.post(f"{BASE}ventas-fraccionadas/{venta_pendiente_a.id}/confirmar/")
        assert resp.status_code == 200
        venta_pendiente_a.refresh_from_db()
        lote_a.refresh_from_db()
        assert venta_pendiente_a.estado == "confirmada"
        assert lote_a.cantidad_actual == Decimal("6.0000")
        assert lote_a.estado == "activo"

    def test_confirmar_agota_lote(self, client_a, lote_a, empresa_a):
        venta = VentaFraccionada.objects.create(
            empresa=empresa_a,
            lote=lote_a,
            cliente_id="CLI-003",
            cantidad=Decimal("10.0000"),
            precio_unit=Decimal("0.0500"),
            monto_total=Decimal("0.5000"),
            estado="pendiente",
        )
        resp = client_a.post(f"{BASE}ventas-fraccionadas/{venta.id}/confirmar/")
        assert resp.status_code == 200
        lote_a.refresh_from_db()
        assert lote_a.cantidad_actual == Decimal("0.0000")
        assert lote_a.estado == "agotado"

    def test_confirmar_no_pendiente_400(self, client_a, venta_pendiente_a):
        venta_pendiente_a.estado = "confirmada"
        venta_pendiente_a.save()
        resp = client_a.post(f"{BASE}ventas-fraccionadas/{venta_pendiente_a.id}/confirmar/")
        assert resp.status_code == 400

    def test_confirmar_stock_insuficiente_400(self, client_a, lote_a, venta_pendiente_a):
        lote_a.cantidad_actual = Decimal("1.0000")
        lote_a.save()
        resp = client_a.post(f"{BASE}ventas-fraccionadas/{venta_pendiente_a.id}/confirmar/")
        assert resp.status_code == 400
        assert "Stock insuficiente" in resp.json()["error"]
        venta_pendiente_a.refresh_from_db()
        assert venta_pendiente_a.estado == "pendiente"

    def test_confirmar_cross_tenant_404(self, client_b, venta_pendiente_a):
        resp = client_b.post(f"{BASE}ventas-fraccionadas/{venta_pendiente_a.id}/confirmar/")
        assert resp.status_code == 404

    def test_b_no_ve_ventas_de_a(self, client_b, venta_pendiente_a):
        resp = client_b.get(f"{BASE}ventas-fraccionadas/")
        assert resp.status_code == 200
        assert str(venta_pendiente_a.id) not in [r["id"] for r in _results(resp)]

    def test_resumen_kpis(self, client_a, lote_a, empresa_a):
        VentaFraccionada.objects.create(
            empresa=empresa_a,
            lote=lote_a,
            cliente_id="CLI-004",
            cantidad=Decimal("2.0000"),
            precio_unit=Decimal("0.0500"),
            monto_total=Decimal("0.1000"),
            estado="confirmada",
        )
        VentaFraccionada.objects.create(
            empresa=empresa_a,
            lote=lote_a,
            cliente_id="CLI-005",
            cantidad=Decimal("1.0000"),
            precio_unit=Decimal("0.0500"),
            monto_total=Decimal("0.0500"),
            estado="pendiente",
        )
        resp = client_a.get(f"{BASE}ventas-fraccionadas/resumen/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lotes_activos"] == 1
        assert data["ventas_mes"] == 1
        assert Decimal(data["ingresos_mes"]) == Decimal("0.1000")
        # Pendiente de cobro: ambas ventas sin pago asociado
        assert Decimal(data["pendiente_cobro"]) == Decimal("0.1500")


class TestPlantillaCobranza:
    def test_create_inyecta_empresa(self, client_a, empresa_a):
        resp = client_a.post(
            f"{BASE}plantillas/",
            {
                "nombre": "Carta formal",
                "canal": "carta",
                "asunto": "Aviso de cobro",
                "cuerpo": "Estimado {cliente}: su saldo es {monto}.",
            },
        )
        assert resp.status_code == 201
        plantilla = PlantillaCobranza.objects.get(nombre="Carta formal")
        assert plantilla.empresa_id == empresa_a.pk

    def test_b_no_ve_plantillas_de_a(self, client_b, plantilla_a):
        resp = client_b.get(f"{BASE}plantillas/")
        assert resp.status_code == 200
        assert str(plantilla_a.id) not in [r["id"] for r in _results(resp)]

    def test_destroy_es_soft_delete(self, client_a, plantilla_a):
        resp = client_a.delete(f"{BASE}plantillas/{plantilla_a.id}/")
        assert resp.status_code == 204
        plantilla_a.refresh_from_db()
        assert plantilla_a.deleted_at is not None


class TestGestionCobranza:
    def test_create_calcula_score_e_inyecta_empresa(self, client_a, empresa_a, user_a):
        resp = client_a.post(
            f"{BASE}gestiones/",
            {
                "cliente_id": "CLI-009",
                "cliente_nombre": "Cliente Nueve",
                "canal": "llamada",
                "resultado": "contactado",
                "fecha_gestion": "2026-06-09",
            },
        )
        assert resp.status_code == 201
        gestion = GestionCobranza.objects.get(cliente_id="CLI-009")
        assert gestion.empresa_id == empresa_a.pk
        assert gestion.gestionado_por_id == user_a.pk
        # Sin cartera ni intentos previos el score degrada a su base
        assert isinstance(gestion.score, Decimal)
        assert gestion.score >= Decimal("0")

    def test_create_score_usa_partida_vencida(self, client_a, empresa_a, monkeypatch):
        """Con una partida vencida en cartera el score sale > 0 (días + monto)."""
        from types import SimpleNamespace

        import apps.cuentas_por_cobrar.services_cartera_provider as provider_mod

        partida = SimpleNamespace(
            cliente_id="CLI-VENC",
            dias_vencida=45,
            monto_pendiente=Decimal("600.00"),
        )

        class _FakeProvider:
            def get_partidas(self, solo_vencidas=False):
                return [partida]

        monkeypatch.setattr(
            provider_mod, "get_cartera_provider", lambda empresa: _FakeProvider()
        )
        resp = client_a.post(
            f"{BASE}gestiones/",
            {
                "cliente_id": "CLI-VENC",
                "canal": "llamada",
                "resultado": "sin_respuesta",
                "fecha_gestion": "2026-06-09",
            },
        )
        assert resp.status_code == 201
        gestion = GestionCobranza.objects.get(cliente_id="CLI-VENC")
        assert gestion.score > Decimal("0")

    def test_create_score_degrada_si_cartera_falla(self, client_a, empresa_a, monkeypatch):
        # M-BUG-7: si la cartera no carga, el score degrada a defaults pero la
        # gestión se crea igual (rama except con logger.warning).
        import apps.cuentas_por_cobrar.services_cartera_provider as provider_mod

        def _boom(empresa):
            raise RuntimeError("cartera caida")

        monkeypatch.setattr(provider_mod, "get_cartera_provider", _boom)
        resp = client_a.post(
            f"{BASE}gestiones/",
            {
                "cliente_id": "CLI-ERR",
                "canal": "email",
                "resultado": "sin_respuesta",
                "fecha_gestion": "2026-06-09",
            },
        )
        assert resp.status_code == 201
        gestion = GestionCobranza.objects.get(cliente_id="CLI-ERR")
        assert gestion.score >= Decimal("0")

    def test_b_no_ve_gestiones_de_a(self, client_b, gestion_a):
        resp = client_b.get(f"{BASE}gestiones/")
        assert resp.status_code == 200
        assert str(gestion_a.id) not in [r["id"] for r in _results(resp)]

    def test_retrieve_gestion_cross_tenant_404(self, client_b, gestion_a):
        resp = client_b.get(f"{BASE}gestiones/{gestion_a.id}/")
        assert resp.status_code == 404

    def test_destroy_es_soft_delete(self, client_a, gestion_a):
        resp = client_a.delete(f"{BASE}gestiones/{gestion_a.id}/")
        assert resp.status_code == 204
        gestion_a.refresh_from_db()
        assert gestion_a.deleted_at is not None

    def test_agenda_proximos_dias(self, client_a, empresa_a, user_a):
        hoy = datetime.date.today()
        dentro = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id="CLI-AG1",
            canal="whatsapp",
            resultado="promesa_pago",
            fecha_gestion=hoy,
            proxima_accion=hoy + datetime.timedelta(days=3),
        )
        fuera = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id="CLI-AG2",
            canal="whatsapp",
            resultado="promesa_pago",
            fecha_gestion=hoy,
            proxima_accion=hoy + datetime.timedelta(days=30),
        )
        resp = client_a.get(f"{BASE}gestiones/agenda/", {"dias": "7"})
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert str(dentro.id) in ids
        assert str(fuera.id) not in ids

    def test_prioridades_cartera_vacia(self, client_a, empresa_a):
        # Provider nativo sin CuentaPorCobrar → lista vacía, 200
        resp = client_a.get(f"{BASE}gestiones/prioridades/", {"limit": "5"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_preview_plantilla_400_sin_plantilla(self, client_a, empresa_a):
        gestion = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id="CLI-NP",
            canal="email",
            resultado="sin_respuesta",
            fecha_gestion=datetime.date(2026, 6, 9),
        )
        resp = client_a.post(f"{BASE}gestiones/{gestion.id}/preview-plantilla/", {})
        assert resp.status_code == 400

    def test_preview_plantilla_renderiza(self, client_a, gestion_a):
        resp = client_a.post(
            f"{BASE}gestiones/{gestion_a.id}/preview-plantilla/",
            {"monto": "150.00", "vencimiento": "2026-06-15", "dias_vencida": "5"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["asunto"] == "Pago pendiente"
        assert data["preview"] == (
            "Hola Cliente Uno, su orden ORD-77 por 150.00 vence el 2026-06-15 (5 días)."
        )


class _FakeAgent:
    """Doble del CobranzaAgent: streaming sin llamar a Anthropic."""

    def __init__(self, empresa_id):
        self.empresa_id = empresa_id

    async def analizar_cartera(self, top_n=10):
        yield f"analisis top {top_n}"

    async def gestionar_cliente(self, cliente_id, instrucciones=""):
        yield f"gestion {cliente_id}: {instrucciones}"


class TestCobranzaAgente:
    def test_rate_limit_429(self, client_a, empresa_a):
        cache.set(f"cxc:agente:ratelimit:{empresa_a.pk}", 10, timeout=3600)
        resp = client_a.post(f"{BASE}agente/", {"accion": "analizar_cartera"})
        assert resp.status_code == 429
        assert "10 llamadas/hora" in resp.json()["error"]

    def test_analizar_cartera_sse(self, client_a, empresa_a, monkeypatch):
        import apps.cxc.agents.cobranza_agent as agent_mod

        monkeypatch.setattr(agent_mod, "CobranzaAgent", _FakeAgent)
        resp = client_a.post(
            f"{BASE}agente/", {"accion": "analizar_cartera", "top_n": "3"}
        )
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/event-stream"
        body = b"".join(resp.streaming_content).decode()
        assert '"text": "analisis top 3"' in body
        assert "data: [DONE]" in body

    def test_gestionar_cliente_sse(self, client_a, empresa_a, monkeypatch):
        import apps.cxc.agents.cobranza_agent as agent_mod

        monkeypatch.setattr(agent_mod, "CobranzaAgent", _FakeAgent)
        resp = client_a.post(
            f"{BASE}agente/",
            {
                "accion": "gestionar_cliente",
                "cliente_id": "CLI-007",
                "instrucciones": "tono amable",
            },
        )
        assert resp.status_code == 200
        body = b"".join(resp.streaming_content).decode()
        assert "gestion CLI-007: tono amable" in body
        assert "data: [DONE]" in body

    def test_error_del_agente_emite_evento_sse_de_error(self, client_a, empresa_a,
                                                         monkeypatch):
        import apps.cxc.agents.cobranza_agent as agent_mod

        class _BrokenAgent:
            def __init__(self, empresa_id):
                pass

            async def analizar_cartera(self, top_n=10):
                raise RuntimeError("agente roto")
                yield  # pragma: no cover — lo convierte en async generator

        monkeypatch.setattr(agent_mod, "CobranzaAgent", _BrokenAgent)
        resp = client_a.post(f"{BASE}agente/", {"accion": "analizar_cartera"})
        assert resp.status_code == 200
        body = b"".join(resp.streaming_content).decode()
        assert '"error"' in body
        # SEC-M4 (R-CODE-8): el detalle interno NO se filtra al cliente.
        assert "agente roto" not in body

    def test_consume_cuota_del_rate_limit(self, client_a, empresa_a, monkeypatch):
        import apps.cxc.agents.cobranza_agent as agent_mod

        monkeypatch.setattr(agent_mod, "CobranzaAgent", _FakeAgent)
        client_a.post(f"{BASE}agente/", {"accion": "analizar_cartera"})
        assert cache.get(f"cxc:agente:ratelimit:{empresa_a.pk}") == 1
