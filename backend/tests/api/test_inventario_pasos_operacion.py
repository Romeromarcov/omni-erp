"""
Tests de PasoOperacion: pasos configurables de operación por almacén/tipo.

Cubre el CRUD API (/api/inventario/pasos-operacion/), el aislamiento multi-tenant
(R-CODE-1), el orden por secuencia y la restricción de unicidad.
"""

from decimal import Decimal  # noqa: F401  (consistencia con otros tests del módulo)

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.almacenes.models import Almacen
from apps.inventario.models import PasoOperacion

pytestmark = pytest.mark.django_db

BASE = "/api/inventario/pasos-operacion/"


@pytest.fixture
def almacen_a(empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Central", codigo_almacen="ALM-PO"
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


def _payload(empresa, almacen, secuencia, nombre, tipo="RECEPCION"):
    return {
        "id_empresa": str(empresa.id_empresa),
        "id_almacen": str(almacen.id_almacen),
        "tipo_operacion": tipo,
        "nombre_paso": nombre,
        "secuencia": secuencia,
    }


def test_crea_y_lista_pasos_ordenados_por_secuencia(client_a, empresa_a, almacen_a):
    # Crear en desorden; la API debe devolverlos ordenados por secuencia.
    for sec, nombre in [(3, "Ubicación"), (1, "Confirmación"), (2, "Calidad")]:
        resp = client_a.post(BASE, _payload(empresa_a, almacen_a, sec, nombre), format="json")
        assert resp.status_code == 201, resp.content

    resp = client_a.get(f"{BASE}?almacen={almacen_a.id_almacen}&tipo_operacion=RECEPCION")
    assert resp.status_code == 200
    data = resp.json()
    items = data["results"] if isinstance(data, dict) and "results" in data else data
    assert [p["nombre_paso"] for p in items] == ["Confirmación", "Calidad", "Ubicación"]


def test_actualiza_y_elimina_paso(client_a, empresa_a, almacen_a):
    paso = PasoOperacion.objects.create(
        id_empresa=empresa_a, id_almacen=almacen_a, tipo_operacion="ENTREGA",
        nombre_paso="Picking", secuencia=1,
    )
    resp = client_a.patch(f"{BASE}{paso.pk}/", {"nombre_paso": "Picking V2"}, format="json")
    assert resp.status_code == 200, resp.content
    paso.refresh_from_db()
    assert paso.nombre_paso == "Picking V2"

    resp = client_a.delete(f"{BASE}{paso.pk}/")
    assert resp.status_code in (204, 200)


def test_aislamiento_tenant(client_b, empresa_a, almacen_a):
    """user_b (empresa_b) no ve los pasos de empresa_a (R-CODE-1)."""
    PasoOperacion.objects.create(
        id_empresa=empresa_a, id_almacen=almacen_a, tipo_operacion="RECEPCION",
        nombre_paso="Confirmación", secuencia=1,
    )
    resp = client_b.get(BASE)
    assert resp.status_code == 200
    data = resp.json()
    items = data["results"] if isinstance(data, dict) and "results" in data else data
    assert items == []


def test_secuencia_unica_por_almacen_y_tipo(empresa_a, almacen_a):
    PasoOperacion.objects.create(
        id_empresa=empresa_a, id_almacen=almacen_a, tipo_operacion="RECEPCION",
        nombre_paso="Confirmación", secuencia=1,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PasoOperacion.objects.create(
                id_empresa=empresa_a, id_almacen=almacen_a, tipo_operacion="RECEPCION",
                nombre_paso="Otro", secuencia=1,
            )


def test_mismo_numero_secuencia_distinto_tipo_ok(empresa_a, almacen_a):
    """La misma secuencia es válida para tipos de operación distintos."""
    PasoOperacion.objects.create(
        id_empresa=empresa_a, id_almacen=almacen_a, tipo_operacion="RECEPCION",
        nombre_paso="Confirmación", secuencia=1,
    )
    paso = PasoOperacion.objects.create(
        id_empresa=empresa_a, id_almacen=almacen_a, tipo_operacion="ENTREGA",
        nombre_paso="Picking", secuencia=1,
    )
    assert paso.pk is not None
