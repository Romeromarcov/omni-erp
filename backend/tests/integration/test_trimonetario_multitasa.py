"""Tests del Motor Trimonetario y Multi-Tasa Extensible (Plan 09 — Ola 1A).

Cubre:
- ``TipoTasaCambio``: CRUD, normalización de código, unicidad y aislamiento multi-tenant
  (tenant B no ve ni edita tipos de A; ningún tenant muta tipos globales como OFICIAL_BCV).
- Múltiples tasas en la MISMA fecha y MISMO par de monedas (``OFICIAL_BCV`` vs ``USDT_P2P``
  vs ``CONVENIDA``), selección por ``codigo_tipo_tasa`` y exigencia estricta
  ``solo_oficial_fiscal=True``.
- ``MonedaEmpresaActiva.es_moneda_referencia``: activación, conmutación atómica entre
  monedas (USDT -> EUR), desactivación y corrección ``es_base``.
- ``calcular_equivalencias_trimonetarias``: Base (USD) + País/Fiscal (VES BCV) +
  Referencia (USDT cuando está activa, None cuando está inactiva), tasa inversa
  automática (VES -> USD) y rechazo de montos negativos.
- Endpoint REST ``POST /api/finanzas/equivalencias-trimonetarias/`` y paridad MCP
  (``finanzas_listar_tipos_tasa`` y ``finanzas_calcular_equivalencias_trimonetarias``).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import CapabilityToken
from apps.finanzas.mcp import (
    finanzas_calcular_equivalencias_trimonetarias,
    finanzas_listar_tipos_tasa,
)
from apps.finanzas.models import Moneda, MonedaEmpresaActiva, TasaCambio, TipoTasaCambio
from apps.finanzas.serializers import MonedaEmpresaActivaSerializer
from apps.finanzas.services import TasaCambioError, convertir_monto, obtener_tasa_cambio
from apps.finanzas.services_trimonetario import (
    calcular_equivalencias_trimonetarias,
    obtener_moneda_referencia_empresa,
    obtener_tasa_por_tipo,
)
from tests.factories import MonedaFactory

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def moneda_ves(db):
    return MonedaFactory(codigo_iso="VES", nombre="Bolívar Soberano", simbolo="Bs", tipo_moneda="fiat")


@pytest.fixture
def moneda_usdt(db):
    return MonedaFactory(codigo_iso="USDT", nombre="Tether USD", simbolo="USDT", tipo_moneda="crypto")


@pytest.fixture
def moneda_eur(db):
    return MonedaFactory(codigo_iso="EUR", nombre="Euro", simbolo="€", tipo_moneda="fiat")


@pytest.fixture
def empresa_trimonetaria(db, empresa_a, moneda_usd, moneda_ves):
    empresa_a.id_moneda_base = moneda_usd
    empresa_a.id_moneda_pais = moneda_ves
    empresa_a.save(update_fields=["id_moneda_base", "id_moneda_pais"])
    return empresa_a


@pytest.fixture
def escenario_tasas_ve(db, empresa_trimonetaria, moneda_usd, moneda_ves, moneda_usdt):
    hoy = timezone.localdate()
    tipo_bcv = TipoTasaCambio.objects.create(
        id_empresa=None,
        codigo="OFICIAL_BCV",
        nombre="Tasa Oficial BCV",
        es_oficial_fiscal=True,
        prioridad=10,
    )
    tipo_usdt = TipoTasaCambio.objects.create(
        id_empresa=empresa_trimonetaria,
        codigo="USDT_P2P",
        nombre="Tasa Mercado USDT P2P",
        es_oficial_fiscal=False,
        prioridad=20,
    )
    tipo_convenida = TipoTasaCambio.objects.create(
        id_empresa=empresa_trimonetaria,
        codigo="CONVENIDA",
        nombre="Tasa Acordada Clientes",
        es_oficial_fiscal=False,
        prioridad=30,
    )

    tasa_bcv = TasaCambio.objects.create(
        id_empresa=None,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        id_tipo_tasa=tipo_bcv,
        tipo_tasa="OFICIAL_BCV",
        valor_tasa=Decimal("888.89000000"),
        fecha_tasa=hoy,
    )
    tasa_usdt_ves = TasaCambio.objects.create(
        id_empresa=empresa_trimonetaria,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        id_tipo_tasa=tipo_usdt,
        tipo_tasa="PERSONALIZADA",
        valor_tasa=Decimal("1350.00000000"),
        fecha_tasa=hoy,
    )
    tasa_convenida = TasaCambio.objects.create(
        id_empresa=empresa_trimonetaria,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        id_tipo_tasa=tipo_convenida,
        tipo_tasa="PERSONALIZADA",
        valor_tasa=Decimal("1100.00000000"),
        fecha_tasa=hoy,
    )
    # Par USD -> USDT (ej. 1 USD = 1.02000000 USDT)
    tasa_usd_usdt = TasaCambio.objects.create(
        id_empresa=empresa_trimonetaria,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_usdt,
        id_tipo_tasa=tipo_usdt,
        tipo_tasa="PERSONALIZADA",
        valor_tasa=Decimal("1.02000000"),
        fecha_tasa=hoy,
    )
    return {
        "fecha": hoy,
        "tipo_bcv": tipo_bcv,
        "tipo_usdt": tipo_usdt,
        "tipo_convenida": tipo_convenida,
        "tasa_bcv": tasa_bcv,
        "tasa_usdt_ves": tasa_usdt_ves,
        "tasa_convenida": tasa_convenida,
        "tasa_usd_usdt": tasa_usd_usdt,
    }


class TestTipoTasaCambioAPIyAislamiento:
    URL = "/api/finanzas/tipos-tasa-cambio/"

    def test_crud_y_normalizacion_codigo(self, client_a, empresa_a):
        resp = client_a.post(
            self.URL,
            {
                "codigo": " usdt_p2p ",
                "nombre": "USDT P2P Mercado",
                "descripcion": "Cotización diaria Binance P2P",
                "prioridad": 15,
            },
            format="json",
        )
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["codigo"] == "USDT_P2P"
        assert data["id_empresa"] == str(empresa_a.id_empresa)

        # Duplicado en la misma empresa devuelve 400
        dup = client_a.post(
            self.URL,
            {"codigo": "usdt_p2p", "nombre": "Duplicado"},
            format="json",
        )
        assert dup.status_code == 400

    def test_aislamiento_cross_tenant_y_proteccion_global(self, client_a, client_b, empresa_a, empresa_b):
        tipo_global = TipoTasaCambio.objects.create(
            id_empresa=None,
            codigo="OFICIAL_BCV",
            nombre="Oficial BCV",
            es_oficial_fiscal=True,
        )
        tipo_a = TipoTasaCambio.objects.create(
            id_empresa=empresa_a,
            codigo="ESPECIAL_A",
            nombre="Especial Empresa A",
        )

        # Empresa B ve el global pero NO el de Empresa A
        resp_list_b = client_b.get(self.URL)
        assert resp_list_b.status_code == 200
        ids_b = {row["id_tipo_tasa"] for row in resp_list_b.json()["results"]}
        assert str(tipo_global.id_tipo_tasa) in ids_b
        assert str(tipo_a.id_tipo_tasa) not in ids_b

        # Empresa B no puede editar ni eliminar el de Empresa A ni el global
        assert (
            client_b.patch(f"{self.URL}{tipo_a.id_tipo_tasa}/", {"nombre": "Hack"}, format="json").status_code == 404
        )
        assert client_b.delete(f"{self.URL}{tipo_a.id_tipo_tasa}/").status_code == 404
        assert (
            client_a.patch(
                f"{self.URL}{tipo_global.id_tipo_tasa}/", {"nombre": "Hack Global"}, format="json"
            ).status_code
            == 403
        )
        assert client_a.delete(f"{self.URL}{tipo_global.id_tipo_tasa}/").status_code == 403

        # POST inyectando id_empresa de Empresa B siendo usuario de A -> 400 (SEC-M1)
        resp_cross = client_a.post(
            self.URL,
            {"id_empresa": str(empresa_b.id_empresa), "codigo": "INYECCION", "nombre": "Ajeno"},
            format="json",
        )
        assert 400 <= resp_cross.status_code < 500


class TestMultiTasaYTrimonetarioServices:
    def test_multiples_tasas_mismo_par_y_solo_oficial_fiscal(
        self, empresa_trimonetaria, moneda_usd, moneda_ves, escenario_tasas_ve
    ):
        hoy = escenario_tasas_ve["fecha"]

        t_usdt = obtener_tasa_por_tipo(
            moneda_usd,
            moneda_ves,
            empresa=empresa_trimonetaria,
            fecha=hoy,
            codigo_tipo_tasa="USDT_P2P",
        )
        assert t_usdt.valor_tasa == Decimal("1350.00000000")

        t_conv = obtener_tasa_cambio(
            moneda_usd,
            moneda_ves,
            empresa=empresa_trimonetaria,
            fecha=hoy,
            codigo_tipo_tasa="CONVENIDA",
        )
        assert t_conv.valor_tasa == Decimal("1100.00000000")

        # Fiscal SIEMPRE exige la tasa oficial (BCV = 888.89), nunca USDT ni Convenida
        t_fiscal = obtener_tasa_por_tipo(
            moneda_usd,
            moneda_ves,
            empresa=empresa_trimonetaria,
            fecha=hoy,
            solo_oficial_fiscal=True,
        )
        assert t_fiscal.valor_tasa == Decimal("888.89000000")

        monto_ves_fiscal = convertir_monto(
            Decimal("100.00"),
            "USD",
            "VES",
            empresa=empresa_trimonetaria,
            fecha=hoy,
            solo_oficial_fiscal=True,
        )
        assert monto_ves_fiscal == Decimal("88889.0000")

    def test_tasa_inversa_automatica(self, empresa_trimonetaria, moneda_usd, moneda_ves, escenario_tasas_ve):
        hoy = escenario_tasas_ve["fecha"]
        t_inv = obtener_tasa_por_tipo(
            moneda_ves,
            moneda_usd,
            empresa=empresa_trimonetaria,
            fecha=hoy,
            solo_oficial_fiscal=True,
        )
        assert getattr(t_inv, "_es_inversa", False) is True
        esperada = (Decimal("1") / Decimal("888.89000000")).quantize(Decimal("0.00000001"))
        assert t_inv.valor_tasa == esperada

    def test_moneda_referencia_toggle_y_conmutacion_atomica(
        self, user_a, empresa_trimonetaria, moneda_usd, moneda_usdt, moneda_eur
    ):
        # Activar USDT como moneda de referencia
        s1 = MonedaEmpresaActivaSerializer(
            data={
                "empresa": str(empresa_trimonetaria.id_empresa),
                "moneda": str(moneda_usdt.id_moneda),
                "activa": True,
                "es_moneda_referencia": True,
            },
            context={"request": type("Req", (), {"user": user_a})()},
        )
        assert s1.is_valid(), s1.errors
        inst_usdt = s1.save()
        assert obtener_moneda_referencia_empresa(empresa_trimonetaria) == moneda_usdt

        # Activar EUR como nueva referencia debe desmarcar automáticamente USDT
        s2 = MonedaEmpresaActivaSerializer(
            data={
                "empresa": str(empresa_trimonetaria.id_empresa),
                "moneda": str(moneda_eur.id_moneda),
                "activa": True,
                "es_moneda_referencia": True,
            },
            context={"request": type("Req", (), {"user": user_a})()},
        )
        assert s2.is_valid(), s2.errors
        inst_eur = s2.save()
        inst_usdt.refresh_from_db()
        assert inst_usdt.es_moneda_referencia is False
        assert inst_eur.es_moneda_referencia is True
        assert obtener_moneda_referencia_empresa(empresa_trimonetaria) == moneda_eur

        # Desactivar EUR apaga la moneda de referencia limpiamente
        s_upd = MonedaEmpresaActivaSerializer(
            inst_eur,
            data={"es_moneda_referencia": False},
            partial=True,
        )
        assert s_upd.is_valid(), s_upd.errors
        s_upd.save()
        assert obtener_moneda_referencia_empresa(empresa_trimonetaria) is None

    def test_equivalencias_trimonetarias_con_y_sin_referencia(
        self, empresa_trimonetaria, moneda_usd, moneda_ves, moneda_usdt, escenario_tasas_ve
    ):
        hoy = escenario_tasas_ve["fecha"]

        # Sin moneda de referencia activa -> devuelve base + país fiscal solamente
        res_sin_ref = calcular_equivalencias_trimonetarias(
            Decimal("100.00"),
            "USD",
            empresa=empresa_trimonetaria,
            fecha=hoy,
        )
        assert res_sin_ref["monto_origen"] == Decimal("100.0000")
        assert res_sin_ref["monto_base"] == Decimal("100.0000")
        assert res_sin_ref["monto_pais_fiscal"] == Decimal("88889.0000")
        assert res_sin_ref["tasa_pais_fiscal"]["es_oficial_fiscal"] is True
        assert res_sin_ref["moneda_referencia_activa"] is False
        assert res_sin_ref["monto_referencia"] is None

        # Activar USDT como moneda de referencia
        MonedaEmpresaActiva.objects.update_or_create(
            empresa=empresa_trimonetaria,
            moneda=moneda_usdt,
            defaults={"activa": True, "es_moneda_referencia": True},
        )
        res_con_ref = calcular_equivalencias_trimonetarias(
            Decimal("100.00"),
            "USD",
            empresa=empresa_trimonetaria,
            fecha=hoy,
        )
        assert res_con_ref["moneda_referencia_activa"] is True
        assert res_con_ref["moneda_referencia_iso"] == "USDT"
        assert res_con_ref["monto_base"] == Decimal("100.0000")
        assert res_con_ref["monto_pais_fiscal"] == Decimal("88889.0000")
        assert res_con_ref["monto_referencia"] == Decimal("102.0000")

        # Monto negativo rechazado
        with pytest.raises(ValueError, match="negativo"):
            calcular_equivalencias_trimonetarias(Decimal("-5"), "USD", empresa=empresa_trimonetaria, fecha=hoy)

    def test_sin_tasa_lanza_error_y_no_asume_uno_a_uno(self, empresa_trimonetaria, moneda_usd, moneda_ves):
        with pytest.raises(TasaCambioError):
            obtener_tasa_por_tipo(
                moneda_usd,
                moneda_ves,
                empresa=empresa_trimonetaria,
                fecha=date(2026, 1, 15),
                solo_oficial_fiscal=True,
            )


class TestEquivalenciasAPIyMCP:
    URL = "/api/finanzas/equivalencias-trimonetarias/"

    def test_api_equivalencias_y_validaciones(
        self, client_a, empresa_trimonetaria, empresa_b, moneda_usd, moneda_usdt, escenario_tasas_ve
    ):
        assert APIClient().post(self.URL, {"monto": "10", "moneda_origen": "USD"}, format="json").status_code == 401

        MonedaEmpresaActiva.objects.update_or_create(
            empresa=empresa_trimonetaria,
            moneda=moneda_usdt,
            defaults={"activa": True, "es_moneda_referencia": True},
        )

        # Por código ISO
        resp = client_a.post(
            self.URL,
            {"monto": "50.00", "moneda_origen": "USD", "fecha": escenario_tasas_ve["fecha"].isoformat()},
            format="json",
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["monto_base"] == "50.0000"
        assert body["monto_pais_fiscal"] == "44444.5000"
        assert body["monto_referencia"] == "51.0000"
        assert body["tasa_pais_fiscal"]["es_oficial_fiscal"] is True

        # Por UUID de moneda privada de otra empresa -> 404
        moneda_privada_b = Moneda.objects.create(
            codigo_iso="PRVB",
            nombre="Privada B",
            simbolo="PB",
            tipo_moneda="crypto",
            es_generica=False,
            es_publica=False,
            empresa=empresa_b,
        )
        resp_ajena = client_a.post(
            self.URL,
            {"monto": "10", "moneda_origen": str(moneda_privada_b.id_moneda)},
            format="json",
        )
        assert resp_ajena.status_code == 404

        # Monto negativo -> 400
        resp_neg = client_a.post(
            self.URL,
            {"monto": "-1", "moneda_origen": "USD"},
            format="json",
        )
        assert resp_neg.status_code == 400

    def test_tasas_cambio_serializer_con_id_tipo_tasa(
        self, client_a, empresa_trimonetaria, moneda_usd, moneda_ves, escenario_tasas_ve
    ):
        resp = client_a.post(
            "/api/finanzas/tasas-cambio/",
            {
                "id_empresa": str(empresa_trimonetaria.id_empresa),
                "id_moneda_origen": str(moneda_usd.id_moneda),
                "id_moneda_destino": str(moneda_ves.id_moneda),
                "id_tipo_tasa": str(escenario_tasas_ve["tipo_usdt"].id_tipo_tasa),
                "valor_tasa": "1365.50000000",
                "fecha_tasa": escenario_tasas_ve["fecha"].isoformat(),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["tipo_tasa"] == "PERSONALIZADA"
        assert data["tipo_tasa_codigo"] == "USDT_P2P"
        assert data["tipo_tasa_nombre"] == "Tasa Mercado USDT P2P"

    def test_mcp_tools_trimonetario(self, empresa_trimonetaria, moneda_usdt, escenario_tasas_ve):
        MonedaEmpresaActiva.objects.update_or_create(
            empresa=empresa_trimonetaria,
            moneda=moneda_usdt,
            defaults={"activa": True, "es_moneda_referencia": True},
        )
        token = CapabilityToken.objects.create(
            empresa=empresa_trimonetaria,
            nombre="tok-trimonetario",
            scopes=["finanzas:read"],
            activo=True,
        )

        tipos = finanzas_listar_tipos_tasa(str(token.token), str(empresa_trimonetaria.id_empresa))
        codigos = {t["codigo"] for t in tipos}
        assert {"OFICIAL_BCV", "USDT_P2P", "CONVENIDA"}.issubset(codigos)

        eq = finanzas_calcular_equivalencias_trimonetarias(
            str(token.token),
            str(empresa_trimonetaria.id_empresa),
            "100.00",
            "USD",
            fecha=escenario_tasas_ve["fecha"].isoformat(),
        )
        assert eq["monto_base"] == Decimal("100.0000")
        assert eq["monto_pais_fiscal"] == Decimal("88889.0000")
        assert eq["monto_referencia"] == Decimal("102.0000")
        assert eq["moneda_referencia_iso"] == "USDT"
