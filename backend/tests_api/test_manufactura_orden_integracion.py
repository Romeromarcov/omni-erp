"""Ola 5.3 — Tests de INTEGRACIÓN (ORM) de la orquestación de manufactura.

Cierra el hueco de cobertura documentado: ejercita crear_orden_produccion,
consumir_materiales_orden (↔ inventario, movimiento CONSUMO_PRODUCCION) y
registrar_produccion_terminada (↔ inventario, ENTRADA al costo real).
"""
from decimal import Decimal

import pytest

from apps.manufactura import services as mfg


def D(x):
    return Decimal(str(x))


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad MFG", abreviatura="UN-MFG", tipo="CANTIDAD"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="MFG")


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén MFG", codigo_almacen="AC-MFG"
    )


def _producto(empresa, unidad, categoria, moneda, nombre, costo):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa,
        nombre_producto=nombre,
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda,
        precio_venta_sugerido=D("0"),
        costo_promedio=D(costo),
    )


@pytest.fixture
def producto_final(db, empresa_a, unidad, categoria, moneda_usd):
    return _producto(empresa_a, unidad, categoria, moneda_usd, "Mesa", "0")


@pytest.fixture
def componente(db, empresa_a, unidad, categoria, moneda_usd):
    return _producto(empresa_a, unidad, categoria, moneda_usd, "Madera", "50")


@pytest.fixture
def stock_componente(db, empresa_a, componente, almacen):
    from apps.inventario.models import StockActual
    return StockActual.objects.create(
        id_empresa=empresa_a, id_producto=componente, id_almacen=almacen,
        cantidad_disponible=D("100"),
    )


@pytest.fixture
def bom(db, empresa_a, producto_final, componente, unidad):
    """BOM: 1 Mesa requiere 4 Maderas."""
    from apps.manufactura.models import ListaMateriales, ListaMaterialesDetalle
    lista = ListaMateriales.objects.create(
        empresa=empresa_a, producto_final=producto_final, nombre="BOM Mesa"
    )
    ListaMaterialesDetalle.objects.create(
        id_lista_materiales=lista, id_producto=componente,
        cantidad_requerida=D("4"), id_unidad_medida=unidad,
    )
    return lista


@pytest.mark.django_db
def test_flujo_orden_produccion_completo(
    empresa_a, producto_final, componente, almacen, stock_componente, bom, user_a
):
    from apps.inventario.models import StockActual

    # 1) Crear OF: 5 Mesas → requiere 20 Maderas.
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=producto_final, cantidad=D("5"), lista_materiales=bom
    )
    assert orden.estado == "pendiente"

    # 2) Consumir materiales (↔ inventario: 100 - 20 = 80).
    res = mfg.consumir_materiales_orden(orden, almacen=almacen, usuario=user_a)
    assert len(res["consumos"]) == 1
    assert res["costo_materiales"] == D("1000")  # 20 maderas * 50
    stock_componente.refresh_from_db()
    assert stock_componente.cantidad_disponible == D("80")
    orden.refresh_from_db()
    assert orden.estado == "en_proceso"

    # 3) Registrar producción terminada (↔ inventario ENTRADA al costo real).
    out = mfg.registrar_produccion_terminada(
        orden, cantidad=D("5"), almacen=almacen, usuario=user_a, mano_obra=D("200")
    )
    # costo total = 1000 materiales + 200 mano de obra = 1200; unitario = 240.
    assert out["costo"]["costo_total"] == D("1200")
    assert out["costo"]["costo_unitario"] == D("240.0000")
    orden.refresh_from_db()
    assert orden.estado == "finalizada"

    # El producto final entró al inventario.
    stock_final = StockActual.objects.get(id_producto=producto_final, id_almacen=almacen)
    assert stock_final.cantidad_disponible == D("5")


@pytest.mark.django_db
def test_consumir_sin_bom_falla(empresa_a, producto_final, almacen, user_a):
    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=producto_final, cantidad=D("1"), lista_materiales=None
    )
    with pytest.raises(mfg.ManufacturaError):
        mfg.consumir_materiales_orden(orden, almacen=almacen, usuario=user_a)
