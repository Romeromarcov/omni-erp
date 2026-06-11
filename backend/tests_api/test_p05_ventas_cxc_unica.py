"""
P0-5 / BUG-A4 — Una sola CuentaPorCobrar por flujo de venta.

Antes del fix:
  - Cliente CREDITO: confirmar_pedido creaba CxC por el subtotal y
    emitir_factura_fiscal creaba OTRA por el total → el cliente debía ~2x.
  - Cliente CONTADO con pedido: entregar_nota_venta asumía "ya tiene CxC" con
    solo verificar que el pedido tenía cliente → la venta entregada y no
    facturada quedaba SIN CxC.

Después del fix:
  - La CxC del flujo nace en confirmar_pedido (CREDITO) o en
    entregar_nota_venta (CONTADO / venta directa).
  - emitir_factura_fiscal REUTILIZA la CxC del flujo, actualizando el monto al
    total fiscal y preservando los abonos registrados.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ── Helpers contables (mismo patrón que test_e2e_ciclo_venta) ─────────────────


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


@pytest.fixture
def mapeo_factura_venta(db, empresa_a):
    from apps.contabilidad.models import MapeoContable
    debe = _cuenta(empresa_a, "P05-1201", "CxC P05", "ACTIVO", "DEUDORA")
    haber = _cuenta(empresa_a, "P05-4101", "Ingresos P05", "INGRESO", "ACREEDORA")
    return MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="FACTURA_VENTA",
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla="FAC {numero}",
        activo=True,
    )


# ── Fixtures de inventario / clientes ─────────────────────────────────────────


@pytest.fixture
def cliente_credito_p05(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Crédito P05",
        rif="J-50505050-5",
        tipo_cliente="CREDITO",
        limite_credito=Decimal("10000.00"),
        dias_credito=30,
    )


@pytest.fixture
def cliente_contado_p05(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Contado P05",
        rif="J-60606060-6",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def producto_p05(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-P05", tipo="CANTIDAD",
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat P05",
    )
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto P05",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("100.00"),
    )


@pytest.fixture
def almacen_p05(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén P05",
        codigo_almacen="ALM-P05",
    )


@pytest.fixture
def stock_p05(db, empresa_a, producto_p05, almacen_p05, user_a):
    from apps.inventario.services import registrar_movimiento
    registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto_p05,
        cantidad=Decimal("100"),
        almacen_destino=almacen_p05,
        usuario=user_a,
    )


def _crear_pedido(empresa, cliente, producto, numero):
    from apps.ventas.models import DetallePedido, Pedido
    pedido = Pedido.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_pedido=numero,
        fecha_pedido=timezone.now().date(),
        estado="PENDIENTE",
    )
    DetallePedido.objects.create(
        id_pedido=pedido,
        id_producto=producto,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("100.00"),
        subtotal=Decimal("200.00"),
    )
    return pedido


def _crear_nota(empresa, cliente, producto, numero, pedido=None):
    from apps.ventas.models import DetalleNotaVenta, NotaVenta
    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        id_pedido_origen=pedido,
        numero_nota=numero,
        fecha_nota=timezone.now().date(),
        estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("100.00"),
        subtotal=Decimal("200.00"),
    )
    return nota


def _cxcs(empresa):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    return CuentaPorCobrar.objects.filter(empresa=empresa).order_by("pk")


# ── Flujo CREDITO: pedido → entrega → factura = 1 sola CxC por el total ───────


class TestFlujoCreditoUnaSolaCxC:
    def test_flujo_credito_completo_una_sola_cxc_por_el_total(
        self, empresa_a, user_a, cliente_credito_p05, producto_p05,
        almacen_p05, stock_p05, moneda_usd, mapeo_factura_venta,
    ):
        from apps.ventas.services import (
            confirmar_pedido,
            emitir_factura_fiscal,
            entregar_nota_venta,
        )

        pedido = _crear_pedido(empresa_a, cliente_credito_p05, producto_p05, "PED-P05-CRED")
        r1 = confirmar_pedido(pedido, almacen_p05, user_a)
        cxc_pedido = r1["cxc"]
        assert cxc_pedido is not None, "Cliente CREDITO debe generar CxC al confirmar"
        assert cxc_pedido.monto == Decimal("200.00")
        assert _cxcs(empresa_a).count() == 1

        nota = _crear_nota(empresa_a, cliente_credito_p05, producto_p05, "NV-P05-CRED", pedido)
        r2 = entregar_nota_venta(nota, almacen_p05, user_a)
        # La entrega NO crea una segunda CxC: reutiliza la del pedido
        assert _cxcs(empresa_a).count() == 1
        assert r2["cxc"].pk == cxc_pedido.pk

        r3 = emitir_factura_fiscal(nota, numero_control="P05-C1", numero_factura="P05-F1", moneda=moneda_usd)
        factura = r3["factura"]
        cxc_final = r3["cxc"]

        # Una sola CxC en todo el flujo, por el TOTAL fiscal de la factura
        assert _cxcs(empresa_a).count() == 1, "El flujo crédito debe dejar UNA sola CxC"
        assert cxc_final.pk == cxc_pedido.pk, "La CxC del pedido debe reutilizarse al facturar"
        assert cxc_final.monto == factura.monto_total.quantize(Decimal("0.01"))
        assert cxc_final.referencia_externa == "P05-F1"
        assert cxc_final.tipo_operacion == "FACTURA_VENTA"
        assert cxc_final.estado == "pendiente"

    def test_flujo_credito_preserva_abonos_al_facturar(
        self, empresa_a, user_a, cliente_credito_p05, producto_p05,
        almacen_p05, stock_p05, moneda_usd, mapeo_factura_venta,
    ):
        """Un abono parcial sobre la CxC del pedido sobrevive a la facturación."""
        from apps.cuentas_por_cobrar.models import AbonoCxC
        from apps.ventas.services import (
            confirmar_pedido,
            emitir_factura_fiscal,
            entregar_nota_venta,
        )

        pedido = _crear_pedido(empresa_a, cliente_credito_p05, producto_p05, "PED-P05-AB")
        cxc = confirmar_pedido(pedido, almacen_p05, user_a)["cxc"]
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=Decimal("50.00"), usuario=user_a)

        nota = _crear_nota(empresa_a, cliente_credito_p05, producto_p05, "NV-P05-AB", pedido)
        entregar_nota_venta(nota, almacen_p05, user_a)
        r = emitir_factura_fiscal(nota, numero_control="P05-C2", numero_factura="P05-F2", moneda=moneda_usd)

        cxc_final = r["cxc"]
        assert cxc_final.pk == cxc.pk
        assert cxc_final.abonos.count() == 1, "El abono previo debe conservarse"
        assert cxc_final.estado == "parcial", "Con abono parcial el estado debe recalcularse a 'parcial'"
        assert _cxcs(empresa_a).count() == 1


# ── Flujo CONTADO con pedido: CxC nace en la entrega ──────────────────────────


class TestFlujoContadoConPedido:
    def test_contado_con_pedido_entregado_sin_facturar_tiene_cxc(
        self, empresa_a, user_a, cliente_contado_p05, producto_p05,
        almacen_p05, stock_p05,
    ):
        """BUG-A4: antes esta venta quedaba SIN CxC; ahora se crea en la entrega."""
        from apps.ventas.services import confirmar_pedido, entregar_nota_venta

        pedido = _crear_pedido(empresa_a, cliente_contado_p05, producto_p05, "PED-P05-CONT")
        r1 = confirmar_pedido(pedido, almacen_p05, user_a)
        assert r1["cxc"] is None, "Cliente CONTADO no genera CxC al confirmar"
        assert _cxcs(empresa_a).count() == 0

        nota = _crear_nota(empresa_a, cliente_contado_p05, producto_p05, "NV-P05-CONT", pedido)
        r2 = entregar_nota_venta(nota, almacen_p05, user_a)

        cxc = r2["cxc"]
        assert cxc is not None, "La entrega de venta CONTADO con pedido debe crear la CxC"
        assert _cxcs(empresa_a).count() == 1
        assert cxc.monto == Decimal("200.00")
        assert cxc.estado == "pendiente"
        assert cxc.tipo_operacion == "NOTA_VENTA"
        assert cxc.empresa_id == empresa_a.id_empresa

    def test_contado_con_pedido_facturado_reutiliza_la_cxc_de_la_entrega(
        self, empresa_a, user_a, cliente_contado_p05, producto_p05,
        almacen_p05, stock_p05, moneda_usd, mapeo_factura_venta,
    ):
        from apps.ventas.services import (
            confirmar_pedido,
            emitir_factura_fiscal,
            entregar_nota_venta,
        )

        pedido = _crear_pedido(empresa_a, cliente_contado_p05, producto_p05, "PED-P05-CF")
        confirmar_pedido(pedido, almacen_p05, user_a)
        nota = _crear_nota(empresa_a, cliente_contado_p05, producto_p05, "NV-P05-CF", pedido)
        cxc_entrega = entregar_nota_venta(nota, almacen_p05, user_a)["cxc"]

        r = emitir_factura_fiscal(nota, numero_control="P05-C3", numero_factura="P05-F3", moneda=moneda_usd)

        assert _cxcs(empresa_a).count() == 1, "Facturar no debe crear una segunda CxC"
        assert r["cxc"].pk == cxc_entrega.pk
        assert r["cxc"].monto == r["factura"].monto_total.quantize(Decimal("0.01"))
        assert r["cxc"].tipo_operacion == "FACTURA_VENTA"


# ── Regresión: venta directa sin pedido ───────────────────────────────────────


class TestVentaDirectaSinPedido:
    def test_venta_directa_sigue_creando_cxc_en_entrega(
        self, empresa_a, user_a, cliente_contado_p05, producto_p05,
        almacen_p05, stock_p05,
    ):
        from apps.ventas.services import entregar_nota_venta

        nota = _crear_nota(empresa_a, cliente_contado_p05, producto_p05, "NV-P05-DIR")
        r = entregar_nota_venta(nota, almacen_p05, user_a)

        assert r["cxc"] is not None
        assert _cxcs(empresa_a).count() == 1
        assert r["cxc"].monto == Decimal("200.00")

    def test_venta_directa_facturada_una_sola_cxc(
        self, empresa_a, user_a, cliente_contado_p05, producto_p05,
        almacen_p05, stock_p05, moneda_usd, mapeo_factura_venta,
    ):
        from apps.ventas.services import emitir_factura_fiscal, entregar_nota_venta

        nota = _crear_nota(empresa_a, cliente_contado_p05, producto_p05, "NV-P05-DIRF")
        cxc_entrega = entregar_nota_venta(nota, almacen_p05, user_a)["cxc"]
        r = emitir_factura_fiscal(nota, numero_control="P05-C4", numero_factura="P05-F4", moneda=moneda_usd)

        assert _cxcs(empresa_a).count() == 1
        assert r["cxc"].pk == cxc_entrega.pk
        assert r["cxc"].monto == r["factura"].monto_total.quantize(Decimal("0.01"))
