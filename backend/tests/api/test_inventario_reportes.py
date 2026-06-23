"""
Tests de los reportes de inventario (existencias, movimientos, valoración).

  T08  Reporte de existencias por producto/almacén.
  T09  Historial de movimientos con filtros (producto, tipo, fecha).
  T10  Valoración FIFO y Promedio correctas.
  T11  Aislamiento multi-tenant en reportes.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.almacenes.models import Almacen
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
from apps.inventario.services import registrar_movimiento

pytestmark = pytest.mark.django_db

EXIST = "/api/inventario/reportes/existencias/"
MOV = "/api/inventario/reportes/movimientos/"
VAL = "/api/inventario/reportes/valoracion/"


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
def almacen(empresa_a):
    return Almacen.objects.create(id_empresa=empresa_a, nombre_almacen="Central", codigo_almacen="ALM-R")


def _producto(empresa_a, moneda_usd, metodo, abbr):
    unidad = UnidadMedida.objects.create(id_empresa=empresa_a, nombre="U", abreviatura=abbr, tipo="CANTIDAD")
    cat = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria=f"Cat {abbr}")
    return Producto.objects.create(
        id_empresa=empresa_a, id_categoria=cat, id_unidad_medida_base=unidad,
        id_moneda_precio=moneda_usd, nombre_producto=f"Prod {abbr}", metodo_valoracion=metodo,
    )


def _entrada(empresa, prod, alm, user, qty, costo):
    registrar_movimiento(
        empresa=empresa, fecha_hora_movimiento=timezone.now(), tipo_movimiento="ENTRADA",
        producto=prod, cantidad=Decimal(str(qty)), almacen_destino=alm,
        costo_unitario=Decimal(str(costo)), usuario=user,
    )


def _salida(empresa, prod, alm, user, qty):
    registrar_movimiento(
        empresa=empresa, fecha_hora_movimiento=timezone.now(), tipo_movimiento="SALIDA",
        producto=prod, cantidad=Decimal(str(qty)), almacen_origen=alm, usuario=user,
    )


# ── T08 — Existencias ─────────────────────────────────────────────────────────


def test_existencias(client_a, empresa_a, almacen, moneda_usd, user_a):
    prod = _producto(empresa_a, moneda_usd, "PROMEDIO", "EX")
    _entrada(empresa_a, prod, almacen, user_a, 10, "5")
    _salida(empresa_a, prod, almacen, user_a, 3)

    resp = client_a.get(EXIST)
    assert resp.status_code == 200
    fila = next(e for e in resp.json()["existencias"] if e["producto_id"] == str(prod.id_producto))
    assert fila["cantidad_disponible"] == "7.0000"

    # Filtro por almacén ajeno → vacío.
    assert client_a.get(f"{EXIST}?almacen=00000000-0000-0000-0000-000000000000").json()["existencias"] == []


# ── T09 — Movimientos con filtros ─────────────────────────────────────────────


def test_movimientos_filtrados(client_a, empresa_a, almacen, moneda_usd, user_a):
    prod = _producto(empresa_a, moneda_usd, "PROMEDIO", "MV")
    _entrada(empresa_a, prod, almacen, user_a, 10, "5")
    _salida(empresa_a, prod, almacen, user_a, 2)

    todos = client_a.get(f"{MOV}?producto={prod.id_producto}").json()["movimientos"]
    assert len(todos) == 2
    solo_salida = client_a.get(f"{MOV}?producto={prod.id_producto}&tipo=SALIDA").json()["movimientos"]
    assert [m["tipo"] for m in solo_salida] == ["SALIDA"]


# ── T10 — Valoración FIFO y Promedio ──────────────────────────────────────────


def test_valoracion_promedio(client_a, empresa_a, almacen, moneda_usd, user_a):
    prod = _producto(empresa_a, moneda_usd, "PROMEDIO", "PR")
    _entrada(empresa_a, prod, almacen, user_a, 10, "10")
    _entrada(empresa_a, prod, almacen, user_a, 10, "20")
    _salida(empresa_a, prod, almacen, user_a, 5)  # promedio 15 → valor salida 75

    fila = next(v for v in client_a.get(VAL).json()["valoracion"] if v["producto_id"] == str(prod.id_producto))
    assert fila["metodo"] == "PROMEDIO"
    assert fila["cantidad"] == "15.0000"
    assert fila["valor_total"] == "225.0000"   # 300 − 75
    assert fila["costo_promedio"] == "15.0000"


def test_valoracion_fifo(client_a, empresa_a, almacen, moneda_usd, user_a):
    prod = _producto(empresa_a, moneda_usd, "FIFO", "FF")
    _entrada(empresa_a, prod, almacen, user_a, 10, "10")
    _entrada(empresa_a, prod, almacen, user_a, 10, "20")
    _salida(empresa_a, prod, almacen, user_a, 15)  # FIFO: 10@10 + 5@20 = 200

    fila = next(v for v in client_a.get(VAL).json()["valoracion"] if v["producto_id"] == str(prod.id_producto))
    assert fila["metodo"] == "FIFO"
    assert fila["cantidad"] == "5.0000"
    assert fila["valor_total"] == "100.0000"    # 300 − 200 (quedan 5 @ 20)
    assert fila["costo_promedio"] == "20.0000"


# ── T11 — Aislamiento ─────────────────────────────────────────────────────────


def test_reportes_aislamiento_tenant(client_b, empresa_a, almacen, moneda_usd, user_a):
    prod = _producto(empresa_a, moneda_usd, "PROMEDIO", "IS")
    _entrada(empresa_a, prod, almacen, user_a, 5, "5")
    assert client_b.get(EXIST).json()["existencias"] == []
    assert client_b.get(VAL).json()["valoracion"] == []
    assert client_b.get(MOV).json()["movimientos"] == []
