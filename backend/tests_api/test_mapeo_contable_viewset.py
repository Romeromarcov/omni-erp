"""
Tests del MapeoContableViewSet (workstream F, PR #94).

R-CODE-1: aislamiento cross-tenant del CRUD de mapeos y rechazo de cuentas
de otra empresa (la validación del serializer, no solo el scope de FK).
"""

import pytest
from rest_framework.test import APIClient

from apps.contabilidad.models import MapeoContable, PlanCuentas

pytestmark = pytest.mark.django_db

BASE = "/api/contabilidad/mapeos-contables/"


def _cuenta(empresa, codigo, naturaleza="DEUDORA"):
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=f"Cuenta {codigo}",
        tipo_cuenta="ACTIVO",
        naturaleza=naturaleza,
        nivel=1,
    )


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
def cuentas_a(empresa_a):
    return _cuenta(empresa_a, "1101"), _cuenta(empresa_a, "2101", "ACREEDORA")


@pytest.fixture
def cuentas_b(empresa_b):
    return _cuenta(empresa_b, "1101"), _cuenta(empresa_b, "2101", "ACREEDORA")


class TestMapeoContableViewSet:
    def test_crear_mapeo_ok(self, client_a, empresa_a, cuentas_a):
        debe, haber = cuentas_a
        r = client_a.post(
            BASE,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_asiento": "CAMBIO_DIVISA",
                "cuenta_debe": str(debe.id_cuenta_contable),
                "cuenta_haber": str(haber.id_cuenta_contable),
            },
            format="json",
        )
        assert r.status_code == 201, r.data
        assert MapeoContable.objects.filter(id_empresa=empresa_a).count() == 1

    def test_aislamiento_lista_y_detalle(self, client_a, client_b, empresa_b, cuentas_b):
        debe, haber = cuentas_b
        mapeo = MapeoContable.objects.create(
            id_empresa=empresa_b, tipo_asiento="NOMINA", cuenta_debe=debe, cuenta_haber=haber
        )
        # B sí lo ve; A no lo lista ni lo recupera (R-CODE-1).
        assert any(
            m["id_mapeo"] == str(mapeo.id_mapeo)
            for m in client_b.get(BASE).data["results"]
        )
        assert all(
            m["id_mapeo"] != str(mapeo.id_mapeo)
            for m in client_a.get(BASE).data["results"]
        )
        assert client_a.get(f"{BASE}{mapeo.id_mapeo}/").status_code == 404

    def test_cuenta_de_otra_empresa_400(self, client_a, empresa_a, cuentas_a, cuentas_b):
        debe_a, _ = cuentas_a
        _, haber_b = cuentas_b
        r = client_a.post(
            BASE,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_asiento": "CAMBIO_DIVISA",
                "cuenta_debe": str(debe_a.id_cuenta_contable),
                "cuenta_haber": str(haber_b.id_cuenta_contable),
            },
            format="json",
        )
        assert r.status_code == 400
        assert MapeoContable.objects.filter(id_empresa=empresa_a).count() == 0

    def test_tipo_asiento_duplicado_400(self, client_a, empresa_a, cuentas_a):
        debe, haber = cuentas_a
        MapeoContable.objects.create(
            id_empresa=empresa_a, tipo_asiento="CAMBIO_DIVISA", cuenta_debe=debe, cuenta_haber=haber
        )
        r = client_a.post(
            BASE,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_asiento": "CAMBIO_DIVISA",
                "cuenta_debe": str(debe.id_cuenta_contable),
                "cuenta_haber": str(haber.id_cuenta_contable),
            },
            format="json",
        )
        assert r.status_code == 400

    def test_tipos_asiento_catalogo(self, client_a):
        r = client_a.get(f"{BASE}tipos-asiento/")
        assert r.status_code == 200
        values = {t["value"] for t in r.data}
        assert {"CAMBIO_DIVISA", "NOMINA", "FACTURA_VENTA"} <= values
