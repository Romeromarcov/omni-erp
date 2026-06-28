"""
Tests del asiento de Costo de Ventas (COGS) al despachar una venta.

Inventario perpetuo: un movimiento DESPACHO_VENTA descarga el inventario contra
Costo de Ventas (DR Costo de Ventas / CR Inventario) valuado al costo real de la
valoración FIFO/Promedio (valor_total). Cubre apps/inventario/services.py.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.almacenes.models import Almacen
from apps.contabilidad.models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas
from apps.inventario.models import CategoriaProducto, Producto, StockActual, UnidadMedida
from apps.inventario.services import registrar_movimiento

pytestmark = pytest.mark.django_db


@pytest.fixture
def cliente(empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Consumidor Final", rif="V-00000000-0",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def almacen(empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Central", codigo_almacen="ALM-COGS"
    )


@pytest.fixture
def producto(empresa_a, moneda_usd):
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-CG", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat COGS")
    return Producto.objects.create(
        id_empresa=empresa_a, id_categoria=categoria, id_unidad_medida_base=unidad,
        id_moneda_precio=moneda_usd, nombre_producto="Producto COGS",
        metodo_valoracion="PROMEDIO",
    )


def _cuenta(empresa, codigo, nombre, tipo="ACTIVO", naturaleza="DEUDORA"):
    return PlanCuentas.objects.create(
        id_empresa=empresa, codigo_cuenta=codigo, nombre_cuenta=nombre,
        tipo_cuenta=tipo, naturaleza=naturaleza, nivel=1,
    )


def _mapeo_costo_venta(empresa):
    costo = _cuenta(empresa, "5.1.01", "Costo de Ventas", tipo="GASTO")
    inventario = _cuenta(empresa, "1.1.05", "Inventario")
    return MapeoContable.objects.create(
        id_empresa=empresa, tipo_asiento="COSTO_VENTA",
        cuenta_debe=costo, cuenta_haber=inventario, activo=True,
    ), costo, inventario


def _nota_borrador(empresa, cliente):
    from apps.ventas.models import NotaVenta

    return NotaVenta.objects.create(
        id_empresa=empresa, id_cliente=cliente,
        numero_nota="NV-COGS-0001", fecha_nota=timezone.now().date(), estado="BORRADOR",
    )


def _entrada(empresa, producto, almacen, user, cantidad, costo):
    registrar_movimiento(
        empresa=empresa, fecha_hora_movimiento=timezone.now(), tipo_movimiento="ENTRADA",
        producto=producto, cantidad=Decimal(str(cantidad)), almacen_destino=almacen,
        costo_unitario=Decimal(str(costo)), usuario=user,
    )


def _despacho(empresa, producto, almacen, user, nota, cantidad):
    return registrar_movimiento(
        empresa=empresa, fecha_hora_movimiento=timezone.now(), tipo_movimiento="DESPACHO_VENTA",
        producto=producto, cantidad=Decimal(str(cantidad)), almacen_origen=almacen,
        documento_origen_id=nota.id_nota_venta, nombre_modelo_origen="NotaVenta", usuario=user,
    )


def test_despacho_genera_asiento_cogs(empresa_a, cliente, almacen, producto, user_a):
    """DESPACHO_VENTA con mapeo COSTO_VENTA → DR Costo de Ventas / CR Inventario == valor_total."""
    _mapeo, costo_cta, inv_cta = _mapeo_costo_venta(empresa_a)
    _entrada(empresa_a, producto, almacen, user_a, 10, "8.00")
    nota = _nota_borrador(empresa_a, cliente)

    mov = _despacho(empresa_a, producto, almacen, user_a, nota, 4)

    asiento = AsientoContable.objects.get(id_documento_origen=mov.pk, nombre_modelo_origen="MovimientoInventario")
    detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
    debe = next(d for d in detalles if d.debe > 0)
    haber = next(d for d in detalles if d.haber > 0)
    assert debe.id_cuenta_contable_id == costo_cta.pk   # DR Costo de Ventas
    assert haber.id_cuenta_contable_id == inv_cta.pk     # CR Inventario
    assert debe.debe == Decimal("32.00")                 # 4 × 8.00 = valor_total
    assert haber.haber == Decimal("32.00")
    assert debe.debe == haber.haber                      # balanceado


def test_despacho_sin_mapeo_contabilidad_inactiva_no_falla(empresa_a, cliente, almacen, producto, user_a):
    """Bodega informal: sin mapeo COSTO_VENTA y contabilidad inactiva → despacho procede sin COGS."""
    assert empresa_a.contabilidad_activa is False
    _entrada(empresa_a, producto, almacen, user_a, 10, "8.00")
    nota = _nota_borrador(empresa_a, cliente)

    mov = _despacho(empresa_a, producto, almacen, user_a, nota, 4)

    assert StockActual.objects.get(id_producto=producto, id_almacen=almacen).cantidad_disponible == Decimal("6.0000")
    assert not AsientoContable.objects.filter(id_documento_origen=mov.pk).exists()


def test_despacho_sin_mapeo_contabilidad_activa_revierte(empresa_a, cliente, almacen, producto, user_a):
    """Contabilidad activa sin mapeo COSTO_VENTA → el despacho revierte (R-CODE-11)."""
    from apps.contabilidad.services import AsientoError

    _entrada(empresa_a, producto, almacen, user_a, 10, "8.00")
    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    nota = _nota_borrador(empresa_a, cliente)
    stock_antes = StockActual.objects.get(id_producto=producto, id_almacen=almacen).cantidad_disponible

    with pytest.raises(AsientoError):
        _despacho(empresa_a, producto, almacen, user_a, nota, 4)

    # Nada persiste: el stock no bajó.
    assert StockActual.objects.get(id_producto=producto, id_almacen=almacen).cantidad_disponible == stock_antes
