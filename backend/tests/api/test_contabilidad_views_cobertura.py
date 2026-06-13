"""
Backfill de cobertura — apps/contabilidad/views.py (plan "Cero Dudas", COV/contabilidad).

Cubre por la API real (`/api/contabilidad/`):
- PlanCuentasViewSet: list aislado por tenant (R-CODE-1), `activos`,
  `por_tipo` con y sin parámetro.
- AsientoContableViewSet: `aprobar` (no-borrador 400, descuadrado 400,
  cuadrado → APROBADO), `anular` (ok / ya anulado 400) y
  `balance_comprobacion` (sin empresa 400, empresa ajena 404 H-SEC-10,
  agregación por cuenta con saldos exactos en Decimal).
- DetalleAsientoViewSet: list aislado vía empresa del asiento padre.
"""
import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.contabilidad.models import AsientoContable, DetalleAsiento, PlanCuentas

pytestmark = pytest.mark.django_db

URL_PLAN = "/api/contabilidad/plan-cuentas/"
URL_ASIENTOS = "/api/contabilidad/asientos-contables/"
URL_DETALLES = "/api/contabilidad/detalles-asiento/"


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
def cuenta_caja(empresa_a):
    return PlanCuentas.objects.create(
        id_empresa=empresa_a, codigo_cuenta="1.1.01", nombre_cuenta="Caja",
        tipo_cuenta="ACTIVO", naturaleza="DEUDORA", nivel=3,
    )


@pytest.fixture
def cuenta_ventas(empresa_a):
    return PlanCuentas.objects.create(
        id_empresa=empresa_a, codigo_cuenta="4.1.01", nombre_cuenta="Ventas",
        tipo_cuenta="INGRESO", naturaleza="ACREEDORA", nivel=3,
    )


@pytest.fixture
def cuenta_inactiva(empresa_a):
    return PlanCuentas.objects.create(
        id_empresa=empresa_a, codigo_cuenta="9.9.99", nombre_cuenta="Obsoleta",
        tipo_cuenta="ACTIVO", naturaleza="DEUDORA", nivel=3, activo=False,
    )


def _asiento(empresa, numero="AS-001", estado="BORRADOR"):
    return AsientoContable.objects.create(
        id_empresa=empresa, fecha_asiento=datetime.date(2026, 6, 1),
        numero_asiento=numero, descripcion="Asiento de prueba",
        estado_asiento=estado,
    )


# ── PlanCuentasViewSet ────────────────────────────────────────────────────────

class TestPlanCuentas:
    def test_list_aislado_por_tenant(self, client_a, client_b, cuenta_caja):
        codigos_a = {c["codigo_cuenta"] for c in client_a.get(URL_PLAN).json()["results"]}
        assert "1.1.01" in codigos_a
        codigos_b = {c["codigo_cuenta"] for c in client_b.get(URL_PLAN).json()["results"]}
        assert "1.1.01" not in codigos_b

    def test_activos_excluye_inactivas(self, client_a, cuenta_caja, cuenta_inactiva):
        resp = client_a.get(f"{URL_PLAN}activos/")
        assert resp.status_code == 200
        codigos = {c["codigo_cuenta"] for c in resp.json()}
        assert codigos == {"1.1.01"}

    def test_por_tipo_con_filtro(self, client_a, cuenta_caja, cuenta_ventas):
        resp = client_a.get(f"{URL_PLAN}por_tipo/", {"tipo": "INGRESO"})
        assert resp.status_code == 200
        codigos = {c["codigo_cuenta"] for c in resp.json()}
        assert codigos == {"4.1.01"}

    def test_por_tipo_sin_filtro_devuelve_activas(
        self, client_a, cuenta_caja, cuenta_ventas, cuenta_inactiva
    ):
        resp = client_a.get(f"{URL_PLAN}por_tipo/")
        codigos = {c["codigo_cuenta"] for c in resp.json()}
        assert codigos == {"1.1.01", "4.1.01"}

    def test_sin_auth_401(self):
        assert APIClient().get(URL_PLAN).status_code == 401


# ── AsientoContableViewSet: aprobar / anular ─────────────────────────────────

class TestAsientoAprobar:
    def test_aprobar_no_borrador_400(self, client_a, empresa_a):
        asiento = _asiento(empresa_a, estado="APROBADO")
        resp = client_a.post(f"{URL_ASIENTOS}{asiento.id_asiento}/aprobar/", {})
        assert resp.status_code == 400
        assert resp.json() == {"error": "Solo se pueden aprobar asientos en estado borrador"}

    def test_aprobar_descuadrado_400(self, client_a, empresa_a, cuenta_caja, cuenta_ventas):
        asiento = _asiento(empresa_a)
        DetalleAsiento.objects.create(
            id_asiento=asiento, id_cuenta_contable=cuenta_caja, debe=Decimal("100.00")
        )
        DetalleAsiento.objects.create(
            id_asiento=asiento, id_cuenta_contable=cuenta_ventas, haber=Decimal("90.00")
        )
        resp = client_a.post(f"{URL_ASIENTOS}{asiento.id_asiento}/aprobar/", {})
        assert resp.status_code == 400
        assert "no cuadra" in resp.json()["error"]
        asiento.refresh_from_db()
        assert asiento.estado_asiento == "BORRADOR"

    def test_aprobar_cuadrado_ok(self, client_a, empresa_a, cuenta_caja, cuenta_ventas):
        asiento = _asiento(empresa_a)
        DetalleAsiento.objects.create(
            id_asiento=asiento, id_cuenta_contable=cuenta_caja, debe=Decimal("100.00")
        )
        DetalleAsiento.objects.create(
            id_asiento=asiento, id_cuenta_contable=cuenta_ventas, haber=Decimal("100.00")
        )
        resp = client_a.post(f"{URL_ASIENTOS}{asiento.id_asiento}/aprobar/", {})
        assert resp.status_code == 200, resp.content
        assert resp.json()["estado_asiento"] == "APROBADO"
        asiento.refresh_from_db()
        assert asiento.estado_asiento == "APROBADO"

    def test_aprobar_asiento_ajeno_404(self, client_b, empresa_a):
        asiento = _asiento(empresa_a)
        resp = client_b.post(f"{URL_ASIENTOS}{asiento.id_asiento}/aprobar/", {})
        assert resp.status_code == 404


class TestAsientoAnular:
    def test_anular_ok(self, client_a, empresa_a):
        asiento = _asiento(empresa_a)
        resp = client_a.post(f"{URL_ASIENTOS}{asiento.id_asiento}/anular/", {})
        assert resp.status_code == 200
        assert resp.json()["estado_asiento"] == "ANULADO"

    def test_anular_ya_anulado_400(self, client_a, empresa_a):
        asiento = _asiento(empresa_a, estado="ANULADO")
        resp = client_a.post(f"{URL_ASIENTOS}{asiento.id_asiento}/anular/", {})
        assert resp.status_code == 400
        assert resp.json() == {"error": "El asiento ya está anulado"}


# ── balance_comprobacion ──────────────────────────────────────────────────────

class TestBalanceComprobacion:
    URL = f"{URL_ASIENTOS}balance_comprobacion/"

    def test_sin_empresa_400(self, client_a):
        resp = client_a.get(self.URL)
        assert resp.status_code == 400
        assert resp.json() == {"error": "Debe especificar el ID de la empresa"}

    def test_empresa_ajena_404(self, client_a, empresa_b):
        """H-SEC-10: empresa no visible para el usuario → 404, sin fuga de datos."""
        resp = client_a.get(self.URL, {"empresa_id": str(empresa_b.id_empresa)})
        assert resp.status_code == 404
        assert resp.json() == {"error": "Empresa no encontrada."}

    def test_agrega_por_cuenta_con_saldos_exactos(
        self, client_a, empresa_a, cuenta_caja, cuenta_ventas
    ):
        # Asiento APROBADO con dos líneas + un BORRADOR que NO debe contar
        aprobado = _asiento(empresa_a, numero="AS-OK", estado="APROBADO")
        DetalleAsiento.objects.create(
            id_asiento=aprobado, id_cuenta_contable=cuenta_caja, debe=Decimal("150.00")
        )
        DetalleAsiento.objects.create(
            id_asiento=aprobado, id_cuenta_contable=cuenta_ventas, haber=Decimal("150.00")
        )
        borrador = _asiento(empresa_a, numero="AS-DRAFT", estado="BORRADOR")
        DetalleAsiento.objects.create(
            id_asiento=borrador, id_cuenta_contable=cuenta_caja, debe=Decimal("999.00")
        )

        resp = client_a.get(self.URL, {"empresa_id": str(empresa_a.id_empresa)})
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert Decimal(str(body["total_debe"])) == Decimal("150.00")
        assert Decimal(str(body["total_haber"])) == Decimal("150.00")
        por_codigo = {c["codigo_cuenta"]: c for c in body["cuentas"]}
        assert Decimal(str(por_codigo["1.1.01"]["saldo"])) == Decimal("150.00")
        assert Decimal(str(por_codigo["4.1.01"]["saldo"])) == Decimal("-150.00")
        assert por_codigo["1.1.01"]["tipo_cuenta"] == "ACTIVO"

    def test_sin_movimientos_devuelve_vacio(self, client_a, empresa_a):
        resp = client_a.get(self.URL, {"empresa_id": str(empresa_a.id_empresa)})
        assert resp.status_code == 200
        assert resp.json()["cuentas"] == []


# ── DetalleAsientoViewSet ─────────────────────────────────────────────────────

class TestDetalleAsiento:
    def test_list_aislado_por_empresa_del_asiento(
        self, client_a, client_b, empresa_a, cuenta_caja
    ):
        asiento = _asiento(empresa_a)
        DetalleAsiento.objects.create(
            id_asiento=asiento, id_cuenta_contable=cuenta_caja, debe=Decimal("10.00")
        )
        data_a = client_a.get(URL_DETALLES).json()
        assert data_a["count"] == 1
        data_b = client_b.get(URL_DETALLES).json()
        assert data_b["count"] == 0
