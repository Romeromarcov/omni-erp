"""
T10 — Producto solo-compra (es_vendible=False) no puede venderse.

``confirmar_pedido`` bloquea cualquier pedido que contenga un producto marcado
como solo-compra; un producto vendible (default) confirma sin problema.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ventas.services import VentaError, confirmar_pedido

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Alm SC", codigo_almacen="ALM-SC"
    )


@pytest.fixture
def cliente(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente SC", rif="J-50505050-5",
        tipo_cliente="CONTADO",
    )


def _producto(empresa, moneda, sku, es_vendible=True):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa, nombre=f"U{sku}", abreviatura=f"U{sku}"[:10], tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria=f"C{sku}")
    return Producto.objects.create(
        id_empresa=empresa, nombre_producto=f"Prod {sku}", sku=sku,
        id_unidad_medida_base=unidad, id_categoria=categoria, id_moneda_precio=moneda,
        es_vendible=es_vendible,
    )


def _pedido_con(empresa, cliente, producto, almacen, user, numero="PED-SC"):
    from apps.inventario.services import registrar_movimiento
    from apps.ventas.models import DetallePedido, Pedido

    # Stock para que la reserva no falle por otra razón.
    registrar_movimiento(
        empresa=empresa, fecha_hora_movimiento=timezone.now(), tipo_movimiento="ENTRADA",
        producto=producto, cantidad=Decimal("100"), almacen_destino=almacen, usuario=user,
    )
    pedido = Pedido.objects.create(
        id_empresa=empresa, id_cliente=cliente, numero_pedido=numero,
        fecha_pedido=timezone.now().date(), estado="PENDIENTE",
    )
    DetallePedido.objects.create(
        id_pedido=pedido, id_producto=producto, cantidad=Decimal("5"),
        precio_unitario=Decimal("50.00"), subtotal=Decimal("250.00"),
    )
    return pedido


class TestProductoSoloCompra:
    def test_pedido_con_producto_solo_compra_se_bloquea(
        self, empresa_a, cliente, almacen, moneda_usd, user_a
    ):
        prod = _producto(empresa_a, moneda_usd, "SOLO-COMP", es_vendible=False)
        pedido = _pedido_con(empresa_a, cliente, prod, almacen, user_a)
        with pytest.raises(VentaError, match="solo-compra"):
            confirmar_pedido(pedido, almacen, user_a)
        pedido.refresh_from_db()
        assert pedido.estado == "PENDIENTE"  # no avanzó

    def test_pedido_con_producto_vendible_confirma(
        self, empresa_a, cliente, almacen, moneda_usd, user_a
    ):
        prod = _producto(empresa_a, moneda_usd, "VEND-OK", es_vendible=True)
        pedido = _pedido_con(empresa_a, cliente, prod, almacen, user_a, numero="PED-OK")
        # No debe lanzar el error de solo-compra (default es_vendible=True).
        resultado = confirmar_pedido(pedido, almacen, user_a)
        assert "reservas" in resultado

    def test_default_es_vendible_true(self, empresa_a, moneda_usd):
        prod = _producto(empresa_a, moneda_usd, "DEF-VEND")
        assert prod.es_vendible is True
        assert prod.es_comprable is True
