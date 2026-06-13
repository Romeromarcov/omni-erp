"""
TEST-5 — Atomicidad del consumo de materiales en manufactura (@transaction.atomic).

`consumir_materiales_orden` explota la BOM y descuenta CADA componente del inventario
(movimiento CONSUMO_PRODUCCION) creando un ConsumoMaterial. Es `@transaction.atomic`,
así que si un componente intermedio falla por stock insuficiente, **toda la operación
debe revertir**: ni consumos parciales, ni descuentos de stock del componente que sí
alcanzaba, ni cambio de estado de la orden.

`tests/integration/test_manufactura_orden_integracion.py` cubre el camino feliz y "sin BOM";
esta es la invariante de rollback multi-escritura que faltaba.
"""

from decimal import Decimal

import pytest

from apps.inventario.services import StockInsuficienteError
from apps.manufactura import services as mfg

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _d(x):
    return Decimal(str(x))


@pytest.fixture
def base_inventario(db, empresa_a, moneda_usd):
    """Unidad, categoría y almacén compartidos."""
    from apps.almacenes.models import Almacen
    from apps.inventario.models import CategoriaProducto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad MFG-AT", abreviatura="UN-MAT", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="MFG-AT")
    almacen = Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén MFG-AT", codigo_almacen="AC-MAT"
    )
    return unidad, categoria, almacen


def _producto(empresa, unidad, categoria, moneda, nombre, costo):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa,
        nombre_producto=nombre,
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda,
        precio_venta_sugerido=_d("0"),
        costo_promedio=_d(costo),
    )


def _stock(empresa, producto, almacen, cantidad):
    from apps.inventario.models import StockActual

    return StockActual.objects.create(
        id_empresa=empresa, id_producto=producto, id_almacen=almacen,
        cantidad_disponible=_d(cantidad),
    )


@pytest.mark.django_db
def test_consumo_revierte_si_un_componente_no_tiene_stock(empresa_a, base_inventario, moneda_usd, user_a):
    """
    BOM de 2 componentes: A tiene stock de sobra, B es insuficiente. Al consumir,
    el componente que falla (B) lanza StockInsuficienteError y TODO revierte:
    sin ConsumoMaterial, sin descuento del componente A, orden sigue 'pendiente'.
    """
    from apps.inventario.models import StockActual
    from apps.manufactura.models import (
        ConsumoMaterial,
        ListaMateriales,
        ListaMaterialesDetalle,
    )

    unidad, categoria, almacen = base_inventario

    producto_final = _producto(empresa_a, unidad, categoria, moneda_usd, "Producto Final AT", "0")
    comp_a = _producto(empresa_a, unidad, categoria, moneda_usd, "Componente A", "50")
    comp_b = _producto(empresa_a, unidad, categoria, moneda_usd, "Componente B", "30")

    # A: 100 disponible (suficiente). B: 10 disponible (insuficiente para 20).
    _stock(empresa_a, comp_a, almacen, "100")
    _stock(empresa_a, comp_b, almacen, "10")

    lista = ListaMateriales.objects.create(
        empresa=empresa_a, producto_final=producto_final, nombre="BOM AT"
    )
    # Cada unidad requiere 4 de A y 4 de B; orden de 5 → 20 de cada uno.
    ListaMaterialesDetalle.objects.create(
        id_lista_materiales=lista, id_producto=comp_a, cantidad_requerida=_d("4"), id_unidad_medida=unidad
    )
    ListaMaterialesDetalle.objects.create(
        id_lista_materiales=lista, id_producto=comp_b, cantidad_requerida=_d("4"), id_unidad_medida=unidad
    )

    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=producto_final, cantidad=_d("5"), lista_materiales=lista
    )
    assert orden.estado == "pendiente"

    with pytest.raises(StockInsuficienteError):
        mfg.consumir_materiales_orden(orden, almacen=almacen, usuario=user_a)

    # Rollback total: ningún consumo, ningún stock tocado, orden intacta.
    assert ConsumoMaterial.objects.filter(orden_produccion=orden).count() == 0, (
        "ATOMICIDAD: quedaron ConsumoMaterial tras el fallo de stock."
    )
    assert StockActual.objects.get(id_producto=comp_a, id_almacen=almacen).cantidad_disponible == _d("100"), (
        "ATOMICIDAD: el stock del componente A se descontó pese al rollback."
    )
    assert StockActual.objects.get(id_producto=comp_b, id_almacen=almacen).cantidad_disponible == _d("10"), (
        "ATOMICIDAD: el stock del componente B cambió pese al rollback."
    )
    orden.refresh_from_db()
    assert orden.estado == "pendiente", "ATOMICIDAD: la orden cambió de estado pese al rollback."
