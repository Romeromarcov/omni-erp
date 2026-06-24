"""
Flujo completo Compras → CxP → Pago (cierre DONE de la serie).

Encadena en una sola prueba el ciclo de adquisición y pago, verificando que los
módulos componen correctamente y que la contabilidad cuadra:

  proveedor → OC + línea → aprobar → recepción (stock + costo + CxP + asiento)
  → factura de compra (asiento) → abono CxP a otra tasa (diferencia cambiaria)
  → aging CxP → asientos balanceados (débitos = créditos) → aislamiento tenant.

Cubre de extremo a extremo: T04 (recepción/stock/costo), T05 (factura/asiento),
T06 (diferencia cambiaria), T07 (pago/CxP), T11 (aging), T12 (balance) y T13
(aislamiento multi-tenant). Las piezas individuales tienen sus propios tests;
este valida la integración del flujo.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.compras.services import aprobar_orden_compra, registrar_factura_compra, registrar_recepcion
from apps.cuentas_por_pagar.services import calcular_aging_cxp, registrar_abono_cxp

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers contables ───────────────────────────────────────────────────────


def _cuenta(empresa, codigo, nombre, tipo="ACTIVO", nat="DEUDORA"):
    from apps.contabilidad.models import PlanCuentas

    return PlanCuentas.objects.create(
        id_empresa=empresa, codigo_cuenta=codigo, nombre_cuenta=nombre,
        tipo_cuenta=tipo, naturaleza=nat, nivel=1,
    )


def _mapeo(empresa, tipo_asiento, debe, haber):
    from apps.contabilidad.models import MapeoContable

    return MapeoContable.objects.create(
        id_empresa=empresa, tipo_asiento=tipo_asiento, cuenta_debe=debe,
        cuenta_haber=haber, descripcion_plantilla=tipo_asiento, activo=True,
    )


def _mapeos_completos(empresa):
    inv = _cuenta(empresa, "1401", "Inventario", "ACTIVO", "DEUDORA")
    cxp = _cuenta(empresa, "2101", "CxP", "PASIVO", "ACREEDORA")
    gasto = _cuenta(empresa, "5101", "Compras", "GASTO", "DEUDORA")
    banco = _cuenta(empresa, "1101", "Banco", "ACTIVO", "DEUDORA")
    perd = _cuenta(empresa, "5701", "Pérdida Cambiaria", "GASTO", "DEUDORA")
    _mapeo(empresa, "RECEPCION_MERCANCIA", inv, cxp)
    _mapeo(empresa, "FACTURA_COMPRA", gasto, cxp)
    _mapeo(empresa, "PAGO_CXP", cxp, banco)
    _mapeo(empresa, "PERDIDA_CAMBIARIA", perd, banco)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def proveedor(db, empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        id_empresa=empresa_a, razon_social="Proveedor Flujo", rif="J-60606060-6"
    )


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Alm Flujo", codigo_almacen="ALM-FL"
    )


@pytest.fixture
def producto(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="U Flujo", abreviatura="U-FL", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat Flujo")
    return Producto.objects.create(
        id_empresa=empresa_a, nombre_producto="Prod Flujo", sku="PROD-FL",
        id_unidad_medida_base=unidad, id_categoria=categoria, id_moneda_precio=moneda_usd,
    )


def _asientos_cuadran(empresa):
    """Todo AsientoContable de la empresa tiene débitos == créditos."""
    from apps.contabilidad.models import AsientoContable

    for asiento in AsientoContable.objects.filter(id_empresa=empresa):
        detalles = list(asiento.detalleasiento_set.all())
        debe = sum(d.debe for d in detalles)
        haber = sum(d.haber for d in detalles)
        if debe != haber:
            return False
    return True


class TestFlujoCompletoComprasPagos:
    def test_ciclo_compra_pago_completo(
        self, empresa_a, empresa_b, proveedor, almacen, producto, user_a
    ):
        from apps.compras.models import DetalleOrdenCompra, OrdenCompra

        _mapeos_completos(empresa_a)

        # 1) OC con una línea (subtotal 1000) → aprobar (sin regla de aprobación).
        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a, id_proveedor=proveedor, numero_orden="OC-FL-1",
            fecha_orden=timezone.now().date(), estado="BORRADOR",
        )
        DetalleOrdenCompra.objects.create(
            id_orden_compra=oc, id_producto=producto, cantidad=Decimal("10"),
            precio_unitario=Decimal("100.00"), subtotal=Decimal("1000.00"),
        )
        aprobar_orden_compra(oc, user_a)
        oc.refresh_from_db()
        assert oc.estado == "APROBADA"

        # 2) Recepción → stock + costo + CxP + asiento RECEPCION_MERCANCIA (T04).
        res = registrar_recepcion(
            oc, almacen, user_a,
            items=[{"producto": producto, "cantidad": "10", "costo_unitario": "100.00"}],
        )
        cxp = res["cxp"]
        assert cxp.monto_total == Decimal("1000.0000")
        assert res["asiento"].nombre_modelo_origen == "RecepcionMercancia"

        from apps.inventario.models import StockActual

        stock = StockActual.objects.get(id_empresa=empresa_a, id_producto=producto, id_almacen=almacen)
        assert stock.cantidad_disponible == Decimal("10")

        # 3) Factura de compra → asiento FACTURA_COMPRA + re-vincula CxP (T05).
        fac = registrar_factura_compra(res["recepcion"], "FC-FL-1", usuario=user_a)
        assert fac["asiento"].nombre_modelo_origen == "FacturaCompra"
        cxp.refresh_from_db()
        assert cxp.id_factura_compra == fac["factura"]

        # 4) Abono parcial a otra tasa → CxP parcial + diferencia cambiaria (T06/T07).
        registrar_abono_cxp(
            cxp, Decimal("400.00"), user_a,
            tasa_original=Decimal("36"), tasa_pago=Decimal("40"),
        )
        cxp.refresh_from_db()
        assert cxp.monto_pendiente == Decimal("600.0000")
        assert cxp.estado == "PARCIAL"

        from apps.cuentas_por_pagar.models import DiferenciaCambiaria

        dif = DiferenciaCambiaria.objects.get(id_empresa=empresa_a)
        assert dif.tipo == "PERDIDA"
        # monto_moneda (400) × |tasa_pago - tasa_original| = 400 × |40-36| = 1600.
        assert dif.monto_diferencia == Decimal("1600.0000")

        # 5) Aging CxP refleja el saldo pendiente (T11).
        aging = calcular_aging_cxp(empresa_a.id_empresa)
        assert aging["total_general"] == Decimal("600.0000")

        # 6) Todos los asientos cuadran (T12).
        assert _asientos_cuadran(empresa_a) is True

        # 7) Aislamiento multi-tenant: empresa_b no ve nada de empresa_a (T13).
        aging_b = calcular_aging_cxp(empresa_b.id_empresa)
        assert aging_b["total_general"] == Decimal("0")
        from apps.cuentas_por_pagar.models import CuentaPorPagar

        assert CuentaPorPagar.objects.filter(id_empresa=empresa_b).count() == 0
