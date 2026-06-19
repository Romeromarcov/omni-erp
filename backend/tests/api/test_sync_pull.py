"""Pull de deltas para clientes offline — CTF-008 Nivel 2 (paso 1).

Verifica el endpoint GET /api/sync/pull/: proyección whitelist, cursor por
`fecha_actualizacion`, propagación de bajas (activo=False), aislamiento
multi-tenant (R-CODE-1), Decimal como string (R-CODE-4) y validaciones.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

URL = "/api/sync/pull/"


@pytest.fixture
def catalogo(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad S", abreviatura="UN-S", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat S")

    def _producto(nombre, sku, costo):
        return Producto.objects.create(
            id_empresa=empresa_a, nombre_producto=nombre, sku=sku,
            id_categoria=categoria, id_unidad_medida_base=unidad,
            id_moneda_precio=moneda_usd, costo_promedio=Decimal(costo),
            precio_venta_sugerido=Decimal("0"),
        )

    p1 = _producto("Silla S", "SKU-S1", "12.3456")
    p2 = _producto("Mesa S", "SKU-S2", "0")
    return {"unidad": unidad, "categoria": categoria, "p1": p1, "p2": p2}


def test_pull_productos_devuelve_catalogo_con_whitelist(client_a, catalogo):
    resp = client_a.get(URL, {"entity": "productos"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity"] == "productos"
    assert body["count"] == 2
    assert body["has_more"] is False
    assert "server_time" in body
    fila = next(r for r in body["results"] if r["sku"] == "SKU-S1")
    # whitelist exacta de la proyección
    assert set(fila) == {
        "id_producto", "nombre_producto", "sku", "id_categoria",
        "id_unidad_medida_base", "id_moneda_precio", "costo_promedio",
        "precio_venta_sugerido", "activo", "fecha_actualizacion",
    }
    # Decimal serializado como string sin pérdida de precisión (R-CODE-4)
    assert fila["costo_promedio"] == "12.3456"


def test_pull_desde_futuro_no_devuelve_nada(client_a, catalogo):
    resp = client_a.get(URL, {"entity": "productos", "desde": "2999-01-01T00:00:00Z"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_pull_cursor_incremental(client_a, catalogo):
    """Tras capturar server_time, solo los registros modificados después se
    devuelven en el siguiente pull."""
    cursor = client_a.get(URL, {"entity": "productos"}).json()["server_time"]
    # Sin cambios desde el cursor → 0.
    vacia = client_a.get(URL, {"entity": "productos", "desde": cursor}).json()
    assert vacia["count"] == 0
    # Tocar un producto lo vuelve a incluir.
    catalogo["p1"].nombre_producto = "Silla S v2"
    catalogo["p1"].save()
    delta = client_a.get(URL, {"entity": "productos", "desde": cursor}).json()
    assert [r["sku"] for r in delta["results"]] == ["SKU-S1"]


def test_pull_propaga_bajas(client_a, catalogo):
    """Un registro inactivo (soft-delete) sigue apareciendo con activo=False para
    que el cliente lo elimine de su réplica."""
    catalogo["p2"].activo = False
    catalogo["p2"].save()
    body = client_a.get(URL, {"entity": "productos"}).json()
    p2 = next(r for r in body["results"] if r["sku"] == "SKU-S2")
    assert p2["activo"] is False


def test_pull_limite_y_has_more(client_a, catalogo):
    body = client_a.get(URL, {"entity": "productos", "limite": 1}).json()
    assert body["count"] == 1
    assert body["has_more"] is True


def test_aislamiento_multitenant(client_b, catalogo):
    """Un usuario de otra empresa no ve el catálogo de empresa_a (R-CODE-1)."""
    body = client_b.get(URL, {"entity": "productos"}).json()
    assert body["count"] == 0


def test_entidad_invalida_400(client_a):
    resp = client_a.get(URL, {"entity": "no_existe"})
    assert resp.status_code == 400
    assert "entidades" in resp.json()


def test_desde_invalido_400(client_a, catalogo):
    resp = client_a.get(URL, {"entity": "productos", "desde": "ayer"})
    assert resp.status_code == 400


def test_limite_invalido_400(client_a, catalogo):
    resp = client_a.get(URL, {"entity": "productos", "limite": "muchos"})
    assert resp.status_code == 400


def test_sin_autenticacion_401(catalogo):
    resp = APIClient().get(URL, {"entity": "productos"})
    assert resp.status_code in (401, 403)


def test_pull_variantes_producto(client_a, empresa_a, catalogo):
    """Las variantes (sin id_empresa propio) se filtran por el de su producto y
    exponen su whitelist."""
    from apps.inventario.models import VarianteProducto

    VarianteProducto.objects.create(
        id_producto=catalogo["p1"], codigo_variante="ROJO-M", sku="SKU-S1-RM"
    )
    body = client_a.get(URL, {"entity": "variantes_producto"}).json()
    assert body["count"] == 1
    fila = body["results"][0]
    assert fila["codigo_variante"] == "ROJO-M"
    assert set(fila) == {
        "id_variante", "id_producto", "codigo_variante", "sku",
        "atributos_json", "activo", "fecha_actualizacion",
    }


def test_variantes_aisladas_por_tenant(client_b, empresa_a, catalogo):
    """Un usuario de otra empresa no ve variantes de empresa_a (vía producto)."""
    from apps.inventario.models import VarianteProducto

    VarianteProducto.objects.create(id_producto=catalogo["p1"], codigo_variante="X")
    assert client_b.get(URL, {"entity": "variantes_producto"}).json()["count"] == 0


def test_pull_clientes(client_a, empresa_a):
    from apps.crm.models import Cliente

    Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente Uno C.A.", rif="J-12345678-9",
    )
    body = client_a.get(URL, {"entity": "clientes"}).json()
    assert body["count"] == 1
    assert body["results"][0]["razon_social"] == "Cliente Uno C.A."
    assert set(body["results"][0]) == {
        "id_cliente", "razon_social", "nombre_comercial", "rif",
        "telefono", "email", "tipo_cliente", "activo", "fecha_actualizacion",
    }
