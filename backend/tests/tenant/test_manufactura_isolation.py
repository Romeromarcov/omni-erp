"""
Tests de aislamiento multi-tenant para el módulo Manufactura — CTF-004.

Verifica que:
1. Usuario A no puede ver ni acceder a registros de Empresa B.
2. perform_create inyecta automáticamente la empresa del usuario.
3. Intentar forzar empresa_id de otra empresa en el payload es ignorado
   (empresa es read_only en el serializer).

Modelos cubiertos: ListaMateriales, RutaProduccion, OrdenProduccion
"""

import pytest

from rest_framework.test import APIClient

from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
from apps.manufactura.models import ListaMateriales, OrdenProduccion, RutaProduccion

pytestmark = pytest.mark.django_db

URL_LISTAS = "/api/manufactura/listas-materiales/"
URL_RUTAS = "/api/manufactura/rutas-produccion/"
URL_ORDENES = "/api/manufactura/ordenes-produccion/"


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def categoria_a(empresa_a):
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Materia Prima A",
    )


@pytest.fixture
def unidad_a(empresa_a):
    return UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad",
        abreviatura="UN",
        tipo="UNIDAD",
    )


@pytest.fixture
def producto_a(empresa_a, categoria_a, unidad_a, moneda_usd):
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto Final A",
        id_categoria=categoria_a,
        id_unidad_medida_base=unidad_a,
        id_moneda_precio=moneda_usd,
    )


@pytest.fixture
def categoria_b(empresa_b):
    return CategoriaProducto.objects.create(
        id_empresa=empresa_b,
        nombre_categoria="Materia Prima B",
    )


@pytest.fixture
def unidad_b(empresa_b):
    return UnidadMedida.objects.create(
        id_empresa=empresa_b,
        nombre="Unidad",
        abreviatura="UN",
        tipo="UNIDAD",
    )


@pytest.fixture
def producto_b(empresa_b, categoria_b, unidad_b, moneda_usd):
    return Producto.objects.create(
        id_empresa=empresa_b,
        nombre_producto="Producto Final B",
        id_categoria=categoria_b,
        id_unidad_medida_base=unidad_b,
        id_moneda_precio=moneda_usd,
    )


@pytest.fixture
def lista_a(empresa_a, producto_a):
    """ListaMateriales de Empresa A."""
    return ListaMateriales.objects.create(
        empresa=empresa_a,
        nombre="BOM Alpha v1",
        producto_final=producto_a,
    )


@pytest.fixture
def lista_b(empresa_b, producto_b):
    """ListaMateriales de Empresa B."""
    return ListaMateriales.objects.create(
        empresa=empresa_b,
        nombre="BOM Beta v1",
        producto_final=producto_b,
    )


@pytest.fixture
def ruta_a(empresa_a):
    """RutaProduccion de Empresa A."""
    return RutaProduccion.objects.create(
        empresa=empresa_a,
        nombre="Ruta Alpha",
    )


@pytest.fixture
def ruta_b(empresa_b):
    """RutaProduccion de Empresa B."""
    return RutaProduccion.objects.create(
        empresa=empresa_b,
        nombre="Ruta Beta",
    )


@pytest.fixture
def orden_a(empresa_a, producto_a):
    """OrdenProduccion de Empresa A."""
    from django.utils import timezone
    return OrdenProduccion.objects.create(
        empresa=empresa_a,
        producto=producto_a,
        cantidad=10,
        fecha_inicio=timezone.now().date(),
    )


@pytest.fixture
def orden_b(empresa_b, producto_b):
    """OrdenProduccion de Empresa B."""
    from django.utils import timezone
    return OrdenProduccion.objects.create(
        empresa=empresa_b,
        producto=producto_b,
        cantidad=5,
        fecha_inicio=timezone.now().date(),
    )


# ── Tests de aislamiento — ListaMateriales ────────────────────────────────────


class TestAislamientoListaMateriales:
    """
    Usuario A no puede ver ni acceder a ListaMateriales de Empresa B.
    """

    def test_listado_solo_devuelve_registros_propios(self, user_a, lista_a, lista_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(URL_LISTAS)

        assert response.status_code == 200
        data = response.data
        ids = [str(item["id"]) for item in (data["results"] if "results" in data else data)]
        assert str(lista_a.id) in ids
        assert str(lista_b.id) not in ids, "Empresa B no debe ser visible para usuario A"

    def test_detalle_de_otra_empresa_devuelve_404(self, user_a, lista_b):
        """GET al detalle de una lista de Empresa B debe devolver 404, no 200."""
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(f"{URL_LISTAS}{lista_b.id}/")

        assert response.status_code == 404, (
            f"Se esperaba 404 al acceder a lista de Empresa B, se obtuvo {response.status_code}"
        )

    def test_crear_lista_inyecta_empresa_del_usuario(self, user_a, empresa_a, producto_a):
        """POST /listas-materiales/ debe asignar empresa_a automáticamente."""
        client = APIClient()
        client.force_authenticate(user=user_a)

        payload = {
            "nombre": "BOM Test Auto",
            "producto_final": str(producto_a.id_producto),
        }
        response = client.post(URL_LISTAS, payload, format="json")

        assert response.status_code == 201
        lista = ListaMateriales.objects.get(id=response.data["id"])
        assert lista.empresa_id == empresa_a.pk, "La empresa debe ser la del usuario, no otra"

    def test_forzar_empresa_ajena_en_payload_es_ignorado(self, user_a, empresa_a, empresa_b, producto_a):
        """El campo empresa es read_only — un payload con empresa_b debe ignorarse."""
        client = APIClient()
        client.force_authenticate(user=user_a)

        payload = {
            "nombre": "BOM Injection Attempt",
            "producto_final": str(producto_a.id_producto),
            "empresa": str(empresa_b.id_empresa),  # intento de inyección
        }
        response = client.post(URL_LISTAS, payload, format="json")

        assert response.status_code == 201
        lista = ListaMateriales.objects.get(id=response.data["id"])
        assert lista.empresa_id == empresa_a.pk, (
            "El payload no debe poder sobrescribir la empresa — debe usarse la del usuario"
        )
        assert lista.empresa_id != empresa_b.pk


# ── Tests de aislamiento — RutaProduccion ────────────────────────────────────


class TestAislamientoRutaProduccion:
    """
    Usuario A no puede ver ni acceder a RutaProduccion de Empresa B.
    """

    def test_listado_solo_devuelve_rutas_propias(self, user_a, ruta_a, ruta_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(URL_RUTAS)

        assert response.status_code == 200
        data = response.data
        ids = [str(item["id"]) for item in (data["results"] if "results" in data else data)]
        assert str(ruta_a.id) in ids
        assert str(ruta_b.id) not in ids, "Ruta de Empresa B no debe ser visible para usuario A"

    def test_detalle_de_otra_empresa_devuelve_404(self, user_a, ruta_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(f"{URL_RUTAS}{ruta_b.id}/")

        assert response.status_code == 404

    def test_crear_ruta_inyecta_empresa_del_usuario(self, user_a, empresa_a):
        client = APIClient()
        client.force_authenticate(user=user_a)

        payload = {"nombre": "Ruta Test Auto"}
        response = client.post(URL_RUTAS, payload, format="json")

        assert response.status_code == 201
        ruta = RutaProduccion.objects.get(id=response.data["id"])
        assert ruta.empresa_id == empresa_a.pk


# ── Tests de aislamiento — OrdenProduccion ───────────────────────────────────


class TestAislamientoOrdenProduccion:
    """
    Usuario A no puede ver ni acceder a OrdenProduccion de Empresa B.
    """

    def test_listado_solo_devuelve_ordenes_propias(self, user_a, orden_a, orden_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(URL_ORDENES)

        assert response.status_code == 200
        data = response.data
        ids = [str(item["id"]) for item in (data["results"] if "results" in data else data)]
        assert str(orden_a.id) in ids
        assert str(orden_b.id) not in ids, "Orden de Empresa B no debe ser visible para usuario A"

    def test_detalle_de_otra_empresa_devuelve_404(self, user_a, orden_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(f"{URL_ORDENES}{orden_b.id}/")

        assert response.status_code == 404

    def test_crear_orden_inyecta_empresa_del_usuario(self, user_a, empresa_a, producto_a):
        from django.utils import timezone

        client = APIClient()
        client.force_authenticate(user=user_a)

        payload = {
            "producto": str(producto_a.id_producto),
            "cantidad": "10.00",
            "fecha_inicio": timezone.now().date().isoformat(),
        }
        response = client.post(URL_ORDENES, payload, format="json")

        assert response.status_code == 201
        orden = OrdenProduccion.objects.get(id=response.data["id"])
        assert orden.empresa_id == empresa_a.pk
