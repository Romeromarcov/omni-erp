"""
TEST-5 — Atomicidad del flujo de compras (R-CODE-11 + @transaction.atomic).

Los tests de servicio existentes (`tests/integration/test_m6_compras.py`) cubren el camino
feliz y el best-effort (contabilidad inactiva → procede sin asiento). Lo que faltaba
—y es la invariante crítica— es probar a NIVEL DE FLUJO que, cuando la empresa exige
contabilidad (`contabilidad_activa=True`) y **falta el mapeo contable**, el asiento
falla duro y **toda la operación se revierte**: no queda recepción, ni movimiento de
inventario, ni stock incrementado, ni cuenta por pagar a medias.

Esto complementa `tests/integration/test_rcode11_centralizado.py`, que sólo verifica la política
del helper `generar_asiento_o_fallar` con mocks, sin ejercer la transacción real del flujo.
"""

from decimal import Decimal

import pytest

from django.utils import timezone

from apps.compras.services import (
    CompraError,
    registrar_factura_compra,
    registrar_recepcion,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers contables ───────────────────────────────────────────────────────────


def _cuenta(empresa, codigo, nombre, tipo="ACTIVO", naturaleza="DEUDORA"):
    from apps.contabilidad.models import PlanCuentas

    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _mapeo(empresa, tipo_asiento, debe, haber):
    from apps.contabilidad.models import MapeoContable

    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo_asiento,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla=f"Asiento {tipo_asiento}",
        activo=True,
    )


# ── Fixtures de dominio ─────────────────────────────────────────────────────────


@pytest.fixture
def empresa_contable(empresa_a):
    """Empresa A con contabilidad EXIGIDA (un asiento faltante debe fallar duro)."""
    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    return empresa_a


@pytest.fixture
def proveedor(db, empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Proveedor Atomicidad S.A.",
        rif="J-20002000-2",
    )


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Atomicidad",
        codigo_almacen="ALM-AT",
    )


@pytest.fixture
def producto(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad AT", abreviatura="UN-AT", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat AT")
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto Atomicidad",
        sku="PROD-AT-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("50.00"),
    )


@pytest.fixture
def orden_aprobada(db, empresa_a, proveedor):
    from apps.compras.models import OrdenCompra

    return OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor,
        numero_orden="OC-AT-001",
        fecha_orden=timezone.now().date(),
        estado="APROBADA",
    )


def _items(producto, cantidad="10", costo="25.00"):
    return [{"producto": producto, "cantidad": cantidad, "costo_unitario": costo}]


# ── Recepción: rollback total cuando falla el asiento ───────────────────────────


class TestRecepcionAtomica:
    def test_recepcion_revierte_todo_si_falta_mapeo_y_contabilidad_activa(
        self, empresa_contable, orden_aprobada, almacen, producto, user_a
    ):
        """
        contabilidad_activa + sin mapeo RECEPCION_MERCANCIA → AsientoError → CompraError,
        y NADA del flujo persiste (recepción, detalle, movimiento, stock, CxP).
        """
        from apps.compras.models import DetalleRecepcionMercancia, RecepcionMercancia
        from apps.cuentas_por_pagar.models import CuentaPorPagar
        from apps.inventario.models import MovimientoInventario, StockActual

        with pytest.raises(CompraError, match="asiento"):
            registrar_recepcion(orden_aprobada, almacen, user_a, _items(producto))

        empresa = empresa_contable
        assert not RecepcionMercancia.objects.filter(id_empresa=empresa).exists(), (
            "ATOMICIDAD: quedó una RecepcionMercancia tras fallar el asiento."
        )
        assert not DetalleRecepcionMercancia.objects.filter(id_recepcion__id_empresa=empresa).exists(), (
            "ATOMICIDAD: quedó un DetalleRecepcionMercancia huérfano."
        )
        assert not MovimientoInventario.objects.filter(id_empresa=empresa).exists(), (
            "ATOMICIDAD: quedó un MovimientoInventario tras el rollback."
        )
        assert not StockActual.objects.filter(
            id_empresa=empresa, id_producto=producto, id_almacen=almacen
        ).exists(), "ATOMICIDAD: el stock se incrementó pese al rollback."
        assert not CuentaPorPagar.objects.filter(id_empresa=empresa).exists(), (
            "ATOMICIDAD: quedó una CuentaPorPagar tras el rollback."
        )

    def test_recepcion_persiste_todo_con_contabilidad_activa_y_mapeo(
        self, empresa_contable, orden_aprobada, almacen, producto, user_a
    ):
        """Camino feliz con contabilidad activa: con mapeo, todo el flujo persiste."""
        from apps.inventario.models import StockActual

        inv = _cuenta(empresa_contable, "1401", "Inventario AT", "ACTIVO", "DEUDORA")
        cxp = _cuenta(empresa_contable, "2101", "CxP AT", "PASIVO", "ACREEDORA")
        _mapeo(empresa_contable, "RECEPCION_MERCANCIA", inv, cxp)

        resultado = registrar_recepcion(orden_aprobada, almacen, user_a, _items(producto, "10", "25.00"))

        assert resultado["asiento"] is not None
        assert resultado["cxp"].monto_total == Decimal("250.00")
        stock = StockActual.objects.get(
            id_empresa=empresa_contable, id_producto=producto, id_almacen=almacen
        )
        assert stock.cantidad_disponible == Decimal("10")


# ── Factura de compra: rollback sin tocar la recepción ya commiteada ────────────


class TestFacturaCompraAtomica:
    def test_factura_revierte_si_falta_mapeo_pero_no_toca_recepcion(
        self, empresa_contable, orden_aprobada, almacen, producto, user_a
    ):
        """
        La recepción (con su mapeo) ya está commiteada; la factura falla por faltar el
        mapeo FACTURA_COMPRA → CompraError. No debe crearse FacturaCompra, y la recepción
        + CxP previas deben quedar intactas.
        """
        from apps.compras.models import FacturaCompra, RecepcionMercancia
        from apps.cuentas_por_pagar.models import CuentaPorPagar

        # Recepción exitosa (sólo mapeamos RECEPCION_MERCANCIA, NO FACTURA_COMPRA).
        inv = _cuenta(empresa_contable, "1402", "Inventario AT2", "ACTIVO", "DEUDORA")
        cxp = _cuenta(empresa_contable, "2102", "CxP AT2", "PASIVO", "ACREEDORA")
        _mapeo(empresa_contable, "RECEPCION_MERCANCIA", inv, cxp)
        res_rec = registrar_recepcion(orden_aprobada, almacen, user_a, _items(producto, "10", "30.00"))
        recepcion = res_rec["recepcion"]

        with pytest.raises(CompraError, match="asiento"):
            registrar_factura_compra(recepcion, "FAC-AT-001")

        assert not FacturaCompra.objects.filter(id_empresa=empresa_contable).exists(), (
            "ATOMICIDAD: quedó una FacturaCompra pese a fallar el asiento."
        )
        # La recepción y la CxP previas siguen intactas (no las arrastró el rollback de la factura).
        assert RecepcionMercancia.objects.filter(pk=recepcion.pk).exists()
        assert CuentaPorPagar.objects.filter(id_empresa=empresa_contable).count() == 1
