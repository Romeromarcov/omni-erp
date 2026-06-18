"""Persistencia del costeo real de una OF como CostoProduccion (Sub-fase 1.I).

Verifica que al cerrar una orden de fabricación se materialicen los registros
`costos.CostoProduccion` a partir del costeo real (materiales + mano de obra +
overhead), de forma idempotente, en la moneda base de la empresa y aislada por
tenant (R-CODE-1/4/11).
"""
from decimal import Decimal

import pytest

from apps.costos.models import CostoProduccion
from apps.costos.services import persistir_costos_orden
from apps.manufactura import services as mfg

pytestmark = pytest.mark.django_db


def D(x):
    return Decimal(str(x))


@pytest.fixture
def escenario(db, empresa_a, moneda_usd):
    """Silla (PT) con BOM 2×Madera@10.00 y 100 de madera en un almacén."""
    from apps.almacenes.models import Almacen
    from apps.inventario.models import (
        CategoriaProducto,
        Producto,
        StockActual,
        UnidadMedida,
    )
    from apps.manufactura.models import ListaMateriales, ListaMaterialesDetalle

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad C", abreviatura="UN-C", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="MFG-C")
    almacen = Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén C", codigo_almacen="ALM-C"
    )

    def _producto(nombre, costo):
        return Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto=nombre,
            id_unidad_medida_base=unidad,
            id_categoria=categoria,
            id_moneda_precio=moneda_usd,
            precio_venta_sugerido=D("0"),
            costo_promedio=D(costo),
        )

    silla = _producto("Silla C", "0")
    madera = _producto("Madera C", "10.00")
    StockActual.objects.create(
        id_empresa=empresa_a, id_producto=madera, id_almacen=almacen,
        cantidad_disponible=D("1000"), cantidad_comprometida=D("0"),
    )
    bom = ListaMateriales.objects.create(empresa=empresa_a, producto_final=silla, nombre="BOM Silla C")
    ListaMaterialesDetalle.objects.create(
        id_lista_materiales=bom, id_producto=madera, cantidad_requerida=D("2"), id_unidad_medida=unidad
    )
    return {"silla": silla, "madera": madera, "bom": bom, "almacen": almacen, "unidad": unidad}


def _crear_consumir(empresa, escenario, user, cantidad="10"):
    orden = mfg.crear_orden_produccion(
        empresa=empresa, producto=escenario["silla"], cantidad=D(cantidad),
        lista_materiales=escenario["bom"],
    )
    mfg.consumir_materiales_orden(orden, almacen=escenario["almacen"], usuario=user)
    return orden


def test_persiste_tres_costos_al_finalizar(escenario, empresa_a, user_a, moneda_usd):
    """Cerrar la OF crea 3 CostoProduccion; el material directo = 2×10×10 = 200,
    mano de obra y overhead en 0 (sin etapas ni config), en la moneda base."""
    orden = _crear_consumir(empresa_a, escenario, user_a)
    res = mfg.registrar_produccion_terminada(
        orden, cantidad=D("10"), almacen=escenario["almacen"], usuario=user_a
    )

    orden.refresh_from_db()
    assert orden.estado == "finalizada"
    assert len(res["costos_persistidos"]) == 3

    costos = {c.tipo_costo: c for c in CostoProduccion.objects.filter(id_orden_produccion=orden)}
    assert set(costos) == {"MATERIAL_DIRECTO", "MANO_OBRA_DIRECTA", "COSTOS_INDIRECTOS"}
    assert costos["MATERIAL_DIRECTO"].costo_total == D("200.0000")
    assert costos["MATERIAL_DIRECTO"].costo_unitario == D("20.0000")
    assert costos["MATERIAL_DIRECTO"].cantidad == D("10")
    assert costos["MANO_OBRA_DIRECTA"].costo_total == D("0.0000")
    assert costos["COSTOS_INDIRECTOS"].costo_total == D("0.0000")
    assert all(c.id_moneda_id == moneda_usd.pk for c in costos.values())
    assert all(c.id_empresa_id == empresa_a.pk for c in costos.values())


def test_incluye_mano_obra_y_overhead(escenario, empresa_a, user_a):
    """Con etapas completadas (mano de obra) y overhead configurado, los costos
    persistidos reflejan ambos y coinciden con costeo_real_orden."""
    from apps.manufactura.models import ConfiguracionManufactura

    mfg.crear_etapas_estandar(empresa_a)
    ConfiguracionManufactura.objects.create(empresa=empresa_a, porcentaje_overhead=D("10"))

    orden = mfg.crear_orden_produccion(
        empresa=empresa_a, producto=escenario["silla"], cantidad=D("10"),
        lista_materiales=escenario["bom"],
    )
    mfg.consumir_materiales_orden(orden, almacen=escenario["almacen"], usuario=user_a)
    # Completar todas las etapas materializadas; una con horas para generar MO.
    primera = True
    while orden.etapas.filter(estado="pendiente").exists():
        mfg.avanzar_etapa_orden(
            orden, usuario=user_a,
            horas_trabajadas=D("5") if primera else D("0"),
            tarifa_hora=D("4") if primera else D("0"),
        )
        primera = False

    esperado = mfg.costeo_real_orden(orden, cantidad_producida=D("10"))
    res = mfg.registrar_produccion_terminada(
        orden, cantidad=D("10"), almacen=escenario["almacen"], usuario=user_a
    )
    assert len(res["costos_persistidos"]) == 3
    costos = {c.tipo_costo: c for c in CostoProduccion.objects.filter(id_orden_produccion=orden)}
    assert costos["MANO_OBRA_DIRECTA"].costo_total == esperado["mano_obra"] == D("20.0000")
    # overhead 10% sobre (materiales 200 + MO 20) = 22
    assert costos["COSTOS_INDIRECTOS"].costo_total == esperado["costos_indirectos"] == D("22.0000")
    assert costos["MATERIAL_DIRECTO"].costo_total == esperado["costo_materiales"] == D("200.0000")


def test_idempotente_no_duplica(escenario, empresa_a, user_a):
    """Re-invocar la persistencia sobre una OF ya costeada no crea duplicados."""
    orden = _crear_consumir(empresa_a, escenario, user_a)
    mfg.registrar_produccion_terminada(
        orden, cantidad=D("10"), almacen=escenario["almacen"], usuario=user_a
    )
    assert CostoProduccion.objects.filter(id_orden_produccion=orden, activo=True).count() == 3

    creados = persistir_costos_orden(orden)
    assert creados == []
    assert CostoProduccion.objects.filter(id_orden_produccion=orden, activo=True).count() == 3


def test_forzar_recostea(escenario, empresa_a, user_a):
    """forzar=True desactiva los previos y recostea (3 activos nuevos)."""
    orden = _crear_consumir(empresa_a, escenario, user_a)
    mfg.registrar_produccion_terminada(
        orden, cantidad=D("10"), almacen=escenario["almacen"], usuario=user_a
    )
    creados = persistir_costos_orden(orden, forzar=True)
    assert len(creados) == 3
    assert CostoProduccion.objects.filter(id_orden_produccion=orden, activo=True).count() == 3
    assert CostoProduccion.objects.filter(id_orden_produccion=orden, activo=False).count() == 3


def test_sin_produccion_usa_cantidad_planificada(escenario, empresa_a, user_a):
    """Llamar a la persistencia antes de registrar producción usa la cantidad
    planificada de la OF como base (fallback producido<=0)."""
    orden = _crear_consumir(empresa_a, escenario, user_a, cantidad="8")
    creados = persistir_costos_orden(orden)
    assert len(creados) == 3
    assert all(c.cantidad == D("8") for c in creados)


def test_empresa_sin_moneda_base_falla(escenario, empresa_a, user_a):
    """Sin moneda base configurada, el costeo no se puede persistir (R-CODE-4)."""
    orden = _crear_consumir(empresa_a, escenario, user_a)
    empresa_a.id_moneda_base = None
    empresa_a.save(update_fields=["id_moneda_base"])
    orden.empresa.refresh_from_db()
    with pytest.raises(mfg.ManufacturaError):
        persistir_costos_orden(orden)
    assert CostoProduccion.objects.filter(id_orden_produccion=orden).count() == 0


def test_produccion_parcial_no_persiste(escenario, empresa_a, user_a):
    """Una producción parcial (OF no finalizada) no materializa costos todavía."""
    orden = _crear_consumir(empresa_a, escenario, user_a, cantidad="10")
    res = mfg.registrar_produccion_terminada(
        orden, cantidad=D("4"), almacen=escenario["almacen"], usuario=user_a
    )
    orden.refresh_from_db()
    assert orden.estado == "parcial"
    assert res["costos_persistidos"] == []
    assert CostoProduccion.objects.filter(id_orden_produccion=orden).count() == 0
