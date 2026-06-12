"""
1.G — Devoluciones POS: integración del service ``registrar_devolucion_pos``.

Montos calculados A MANO en cada test (sin reusar la lógica del service):

  Venta no fiscal: 10 und × 5.00 = 50.00 (sin IVA hasta facturar).
  Venta fiscal:    base 50.00 + IVA 16% = 8.00 → total 58.00.

Cubre, todo dentro de UNA transacción (R-CODE-11):
  - reingreso de stock al almacén;
  - nota de crédito interna (venta no fiscal) y FISCAL (venta facturada:
    correlativo NOTA_CREDITO + numero_control compartido + IVA proporcional);
  - reverso del dinero: Pago EGRESO en la caja física de la sesión abierta;
  - asiento de reverso cuadrado (DEVOLUCION_VENTA / DEVOLUCION_VENTA_IVA);
  - sobre-devolución rechazada (acumulado por línea/producto);
  - parcial dos veces hasta el límite exacto;
  - atomicidad: si falta el mapeo contable con contabilidad activa, NADA persiste.
"""

from decimal import Decimal

import pytest

from django.utils import timezone

from apps.contabilidad.models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas
from apps.finanzas.models import (
    CajaFisica,
    MetodoPago,
    Pago,
    SesionCajaFisica,
    TransaccionFinanciera,
)
from apps.inventario.models import StockActual
from apps.ventas.models import (
    DetalleNotaVenta,
    DevolucionVenta,
    NotaCreditoFiscal,
    NotaCreditoVenta,
    NotaVenta,
)
from apps.ventas.services import (
    VentaError,
    confirmar_nota_venta,
    emitir_factura_fiscal,
    registrar_devolucion_pos,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers contables (patrón de tests/integration/test_compras_atomicidad.py) ──


def _cuenta(empresa, codigo, nombre, tipo="ACTIVO", naturaleza="DEUDORA"):
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _mapeo(empresa, tipo_asiento, debe, haber):
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo_asiento,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla=f"Asiento {tipo_asiento}",
        activo=True,
    )


def _mapeos_venta_y_devolucion(empresa):
    """Mapeos mínimos del flujo: venta (NOTA_VENTA/FACTURA) y su reverso."""
    caja = _cuenta(empresa, "1.1.01", "Caja")
    cxc = _cuenta(empresa, "1.1.02", "Cuentas por Cobrar")
    ingresos = _cuenta(empresa, "4.1.01", "Ingresos por Ventas", tipo="INGRESO", naturaleza="ACREEDORA")
    iva_debito = _cuenta(empresa, "2.1.05", "IVA Débito Fiscal", tipo="PASIVO", naturaleza="ACREEDORA")
    devoluciones = _cuenta(empresa, "4.2.01", "Devoluciones en Ventas", tipo="INGRESO", naturaleza="DEUDORA")
    _mapeo(empresa, "NOTA_VENTA", cxc, ingresos)
    _mapeo(empresa, "FACTURA_VENTA", cxc, ingresos)
    _mapeo(empresa, "FACTURA_VENTA_IVA", cxc, iva_debito)
    # Espejo del asiento de venta: el reverso debita devoluciones y acredita caja.
    _mapeo(empresa, "DEVOLUCION_VENTA", devoluciones, caja)
    _mapeo(empresa, "DEVOLUCION_VENTA_IVA", iva_debito, caja)


# ── Fixtures de dominio ──────────────────────────────────────────────────────


@pytest.fixture
def cliente(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Consumidor Final",
        rif="V-00000000-0",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Almacén POS", codigo_almacen="ALM-POS"
    )


@pytest.fixture
def producto(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad POS", abreviatura="UN-POS", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat POS")
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Harina PAN",
        sku="HAR-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("5.00"),
    )


@pytest.fixture
def metodo_efectivo_pos(db):
    return MetodoPago.objects.create(
        nombre_metodo="Efectivo POS", tipo_metodo="EFECTIVO", es_publico=True
    )


@pytest.fixture
def caja_fisica(db, empresa_a):
    return CajaFisica.objects.create(
        empresa=empresa_a,
        nombre="Caja Mostrador",
        identificador_dispositivo="POS-TEST-001",
    )


@pytest.fixture
def sesion_abierta(db, empresa_a, user_a, caja_fisica):
    return SesionCajaFisica.objects.create(
        caja_fisica=caja_fisica, usuario=user_a, empresa=empresa_a, estado="ABIERTA"
    )


def _stock_inicial(empresa, producto, almacen, cantidad, usuario):
    from apps.inventario.services import registrar_movimiento

    registrar_movimiento(
        empresa=empresa,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto,
        cantidad=Decimal(str(cantidad)),
        almacen_destino=almacen,
        usuario=usuario,
        observaciones="Carga inicial test",
    )


def _venta_entregada(empresa, cliente, producto, almacen, usuario, cantidad="10", precio="5.00"):
    """Venta POS completa hasta ENTREGADA (stock fuera + asiento NOTA_VENTA)."""
    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_nota=f"NV-POS-{NotaVenta.objects.count() + 1:04d}",
        fecha_nota=timezone.now().date(),
        estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto,
        cantidad=Decimal(cantidad),
        precio_unitario=Decimal(precio),
        subtotal=Decimal(cantidad) * Decimal(precio),
    )
    confirmar_nota_venta(nota, almacen, usuario)
    nota.refresh_from_db()
    return nota


def _disponible(producto, almacen):
    stock = StockActual.objects.filter(id_producto=producto, id_almacen=almacen).first()
    return stock.cantidad_disponible if stock else Decimal("0")


def _lineas(nota, cantidad):
    detalle = nota.detalles.first()
    return [{"id_detalle": str(detalle.id_detalle_nota_venta), "cantidad": cantidad}]


# ── Devolución de venta NO fiscal ────────────────────────────────────────────


class TestDevolucionNoFiscal:
    def test_devolucion_parcial_stock_caja_nc_y_asiento(
        self, empresa_a, cliente, producto, almacen, user_a, metodo_efectivo_pos, sesion_abierta
    ):
        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)
        assert _disponible(producto, almacen) == Decimal("0")

        resultado = registrar_devolucion_pos(
            nota_venta=nota,
            lineas=_lineas(nota, "4"),
            almacen=almacen,
            usuario=user_a,
            metodo_pago=metodo_efectivo_pos,
            motivo="CAMBIO_CLIENTE",
        )

        # Stock: reingresan exactamente 4 unidades.
        assert _disponible(producto, almacen) == Decimal("4")
        mov = resultado["movimientos"][0]
        assert mov.tipo_movimiento == "ENTRADA"
        assert mov.nombre_modelo_origen == "DevolucionVenta"

        # Devolución: 4 × 5.00 = 20.00 (a mano), referenciada a la venta.
        devolucion = resultado["devolucion"]
        assert devolucion.monto_total == Decimal("20.0000")
        assert devolucion.estado == "PROCESADA"
        assert devolucion.id_nota_venta_origen_id == nota.pk
        assert devolucion.id_factura_origen_id is None
        assert devolucion.id_empresa_id == empresa_a.pk

        # NC interna (la venta no fue fiscal): 20.00 y enlazada a la devolución.
        ncv = resultado["nota_credito_venta"]
        assert resultado["nota_credito_fiscal"] is None
        assert ncv.monto_total == Decimal("20.0000")
        assert ncv.motivo == "DEVOLUCION"
        devolucion.refresh_from_db()
        assert devolucion.id_nota_credito_generada_id == ncv.pk

        # Dinero: Pago EGRESO de 20.00 en la caja física de la sesión abierta.
        pago = resultado["pago"]
        assert pago.tipo_operacion == "EGRESO"
        assert pago.monto == Decimal("20.0000")
        assert pago.id_caja_fisica_id == sesion_abierta.caja_fisica_id
        trans = TransaccionFinanciera.objects.get(pago_asociado=pago)
        assert trans.tipo_transaccion == "EGRESO"
        assert trans.monto_transaccion == Decimal("20.0000")

        # Asiento de reverso cuadrado: debe 20.00 = haber 20.00.
        asiento = resultado["asiento"]
        assert asiento is not None
        detalles = list(DetalleAsiento.objects.filter(id_asiento=asiento))
        assert sum(d.debe for d in detalles) == Decimal("20.0000")
        assert sum(d.haber for d in detalles) == Decimal("20.0000")
        assert resultado["asiento_iva"] is None  # sin IVA: la venta no fue fiscal

    def test_parcial_dos_veces_hasta_el_limite_y_sobre_devolucion_rechazada(
        self, empresa_a, cliente, producto, almacen, user_a, metodo_efectivo_pos, sesion_abierta
    ):
        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)  # vendió 10

        registrar_devolucion_pos(
            nota_venta=nota, lineas=_lineas(nota, "6"), almacen=almacen,
            usuario=user_a, metodo_pago=metodo_efectivo_pos,
        )

        # Segunda devolución que EXCEDE el acumulado (6 + 5 > 10) → rechazada.
        with pytest.raises(VentaError, match="más de lo vendido"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "5"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )

        # Hasta el límite exacto (6 + 4 = 10) → permitida.
        registrar_devolucion_pos(
            nota_venta=nota, lineas=_lineas(nota, "4"), almacen=almacen,
            usuario=user_a, metodo_pago=metodo_efectivo_pos,
        )
        assert _disponible(producto, almacen) == Decimal("10")
        assert DevolucionVenta.objects.filter(id_nota_venta_origen=nota).count() == 2

        # Todo devuelto: una unidad más → rechazada.
        with pytest.raises(VentaError, match="más de lo vendido"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "1"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )

    def test_sin_sesion_de_caja_abierta_rechaza(
        self, empresa_a, cliente, producto, almacen, user_a, metodo_efectivo_pos
    ):
        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)

        with pytest.raises(VentaError, match="sesión de caja"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "1"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )

    def test_venta_no_entregada_rechaza(
        self, empresa_a, cliente, producto, almacen, user_a, metodo_efectivo_pos, sesion_abierta
    ):
        nota = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_nota="NV-BORRADOR-1",
            fecha_nota=timezone.now().date(),
            estado="BORRADOR",  # nunca salió stock: no hay nada que devolver
        )
        DetalleNotaVenta.objects.create(
            id_nota_venta=nota, id_producto=producto,
            cantidad=Decimal("1"), precio_unitario=Decimal("5.00"), subtotal=Decimal("5.00"),
        )
        with pytest.raises(VentaError, match="ENTREGADAS o FACTURADAS"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "1"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )

    def test_linea_ajena_y_cantidades_invalidas_rechazan(
        self, empresa_a, cliente, producto, almacen, user_a, metodo_efectivo_pos, sesion_abierta
    ):
        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 20, user_a)
        nota = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)
        otra = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)

        # Línea de OTRA venta.
        with pytest.raises(VentaError, match="no pertenece a esta venta"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(otra, "1"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )
        # Cantidad cero / negativa / no numérica.
        for cantidad in ("0", "-3"):
            with pytest.raises(VentaError, match="mayor que cero"):
                registrar_devolucion_pos(
                    nota_venta=nota, lineas=_lineas(nota, cantidad), almacen=almacen,
                    usuario=user_a, metodo_pago=metodo_efectivo_pos,
                )
        with pytest.raises(VentaError, match="Cantidad inválida"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "abc"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )
        # Motivo fuera del catálogo.
        with pytest.raises(VentaError, match="Motivo de devolución inválido"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "1"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos, motivo="NO_EXISTE",
            )

    def test_almacen_de_otra_empresa_rechaza(
        self, empresa_a, empresa_b, cliente, producto, almacen, user_a,
        metodo_efectivo_pos, sesion_abierta,
    ):
        from apps.almacenes.models import Almacen

        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)
        almacen_b = Almacen.objects.create(
            id_empresa=empresa_b, nombre_almacen="Almacén B", codigo_almacen="ALM-B"
        )
        # R-CODE-1: el service rechaza el almacén ajeno aunque el caller lo pase.
        with pytest.raises(VentaError, match="almacén no pertenece"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "1"), almacen=almacen_b,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )


# ── Devolución de venta FISCAL ───────────────────────────────────────────────


class TestDevolucionFiscal:
    def _venta_facturada(self, empresa, cliente, producto, almacen, usuario, moneda):
        """Venta ENTREGADA y FACTURADA: base 50.00, IVA 16% = 8.00, total 58.00."""
        nota = _venta_entregada(empresa, cliente, producto, almacen, usuario)  # 10 × 5.00
        resultado = emitir_factura_fiscal(nota, moneda=moneda)
        nota.refresh_from_db()
        factura = resultado["factura"]
        # Sanity de los montos calculados a mano (IVA default SENIAT 16 %).
        assert factura.base_imponible == Decimal("50.00")
        assert factura.monto_iva == Decimal("8.00")
        assert factura.monto_total == Decimal("58.00")
        return nota, factura

    def test_devolucion_total_emite_nc_fiscal_espejo(
        self, empresa_a, cliente, producto, almacen, user_a, moneda_usd,
        metodo_efectivo_pos, sesion_abierta,
    ):
        from apps.fiscal.models import NumeroCorrelativo

        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota, factura = self._venta_facturada(
            empresa_a, cliente, producto, almacen, user_a, moneda_usd
        )

        resultado = registrar_devolucion_pos(
            nota_venta=nota, lineas=_lineas(nota, "10"), almacen=almacen,
            usuario=user_a, metodo_pago=metodo_efectivo_pos, motivo="DEFECTO",
        )

        # NC fiscal espejo de la factura: base 50.00 + IVA 8.00 = 58.00.
        ncf = resultado["nota_credito_fiscal"]
        assert resultado["nota_credito_venta"] is None
        assert ncf.base_imponible == Decimal("50.0000")
        assert ncf.monto_iva == Decimal("8.00")
        assert ncf.monto_total == Decimal("58.0000")
        assert ncf.id_factura_origen_id == factura.pk
        assert ncf.numero_control == factura.numero_control  # control compartido
        assert ncf.estado == "EMITIDA"
        assert ncf.motivo == "DEVOLUCION"
        # Correlativo NOTA_CREDITO existente consumido (1 → 00000001).
        correlativo = NumeroCorrelativo.objects.get(id_empresa=empresa_a, tipo="NOTA_CREDITO")
        assert correlativo.numero_actual == 1
        assert ncf.numero_nota_credito.endswith("00000001")
        detalle_ncf = ncf.detalles.get()
        assert detalle_ncf.cantidad == Decimal("10")
        assert detalle_ncf.monto_impuesto == Decimal("8.00")
        assert detalle_ncf.total_linea == Decimal("58.0000")

        # Devolución referencia AMBOS documentos originales.
        devolucion = resultado["devolucion"]
        assert devolucion.id_factura_origen_id == factura.pk
        assert devolucion.id_nota_venta_origen_id == nota.pk
        assert devolucion.monto_total == Decimal("58.0000")

        # Dinero: EGRESO por el total con IVA (58.00) en la caja de la sesión.
        assert resultado["pago"].monto == Decimal("58.0000")
        assert resultado["pago"].id_moneda_id == factura.id_moneda_id

        # Stock total de vuelta.
        assert _disponible(producto, almacen) == Decimal("10")

        # Asientos de reverso cuadrados: total 58.00 y IVA 8.00.
        asiento = resultado["asiento"]
        det_total = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert sum(d.debe for d in det_total) == Decimal("58.0000")
        assert sum(d.haber for d in det_total) == Decimal("58.0000")
        asiento_iva = resultado["asiento_iva"]
        assert asiento_iva is not None
        det_iva = DetalleAsiento.objects.filter(id_asiento=asiento_iva)
        assert sum(d.debe for d in det_iva) == Decimal("8.00")
        assert sum(d.haber for d in det_iva) == Decimal("8.00")

    def test_devolucion_parcial_fiscal_iva_proporcional(
        self, empresa_a, cliente, producto, almacen, user_a, moneda_usd,
        metodo_efectivo_pos, sesion_abierta,
    ):
        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota, factura = self._venta_facturada(
            empresa_a, cliente, producto, almacen, user_a, moneda_usd
        )

        # Devuelve 4 de 10: base 20.00; IVA proporcional 20 × (8/50) = 3.20.
        resultado = registrar_devolucion_pos(
            nota_venta=nota, lineas=_lineas(nota, "4"), almacen=almacen,
            usuario=user_a, metodo_pago=metodo_efectivo_pos,
        )
        ncf = resultado["nota_credito_fiscal"]
        assert ncf.base_imponible == Decimal("20.0000")
        assert ncf.monto_iva == Decimal("3.20")
        assert ncf.monto_total == Decimal("23.2000")
        assert resultado["pago"].monto == Decimal("23.2000")
        assert resultado["asiento_iva"] is not None

    def test_factura_anulada_rechaza(
        self, empresa_a, cliente, producto, almacen, user_a, moneda_usd,
        metodo_efectivo_pos, sesion_abierta,
    ):
        _mapeos_venta_y_devolucion(empresa_a)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota, factura = self._venta_facturada(
            empresa_a, cliente, producto, almacen, user_a, moneda_usd
        )
        factura.estado = "ANULADA"
        factura.save(update_fields=["estado"])
        with pytest.raises(VentaError, match="ANULADA"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "1"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )


# ── Atomicidad R-CODE-11 ─────────────────────────────────────────────────────


class TestDevolucionAtomicidad:
    def test_sin_mapeo_contable_con_contabilidad_activa_revierte_todo(
        self, empresa_a, cliente, producto, almacen, user_a, metodo_efectivo_pos, sesion_abierta
    ):
        """Falta el mapeo DEVOLUCION_VENTA y la empresa exige contabilidad:
        el asiento falla duro y NO queda stock, ni devolución, ni NC, ni pago."""
        # Solo los mapeos de la venta — el de devolución NO existe.
        cxc = _cuenta(empresa_a, "1.1.02", "CxC")
        ingresos = _cuenta(empresa_a, "4.1.01", "Ingresos", tipo="INGRESO", naturaleza="ACREEDORA")
        _mapeo(empresa_a, "NOTA_VENTA", cxc, ingresos)

        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)

        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])

        stock_antes = _disponible(producto, almacen)
        with pytest.raises(Exception, match="Mapeo Contable"):
            registrar_devolucion_pos(
                nota_venta=nota, lineas=_lineas(nota, "4"), almacen=almacen,
                usuario=user_a, metodo_pago=metodo_efectivo_pos,
            )

        # NADA persiste: ni stock, ni devolución, ni NC, ni pago, ni transacción.
        assert _disponible(producto, almacen) == stock_antes
        assert DevolucionVenta.objects.filter(id_nota_venta_origen=nota).count() == 0
        assert NotaCreditoVenta.objects.filter(id_empresa=empresa_a).count() == 0
        assert NotaCreditoFiscal.objects.filter(id_empresa=empresa_a).count() == 0
        assert Pago.objects.filter(id_empresa=empresa_a, tipo_operacion="EGRESO").count() == 0
        assert TransaccionFinanciera.objects.filter(
            id_empresa=empresa_a, tipo_transaccion="EGRESO"
        ).count() == 0

    def test_sin_mapeo_con_contabilidad_inactiva_procede_sin_asiento(
        self, empresa_a, cliente, producto, almacen, user_a, metodo_efectivo_pos, sesion_abierta
    ):
        """Bodega informal (R-PROD-3): sin mapeo y contabilidad inactiva,
        la devolución procede y reporta asiento_error en vez de romper."""
        cxc = _cuenta(empresa_a, "1.1.02", "CxC")
        ingresos = _cuenta(empresa_a, "4.1.01", "Ingresos", tipo="INGRESO", naturaleza="ACREEDORA")
        _mapeo(empresa_a, "NOTA_VENTA", cxc, ingresos)
        _stock_inicial(empresa_a, producto, almacen, 10, user_a)
        nota = _venta_entregada(empresa_a, cliente, producto, almacen, user_a)

        resultado = registrar_devolucion_pos(
            nota_venta=nota, lineas=_lineas(nota, "2"), almacen=almacen,
            usuario=user_a, metodo_pago=metodo_efectivo_pos,
        )
        assert resultado["asiento"] is None
        assert resultado["asiento_error"]
        assert _disponible(producto, almacen) == Decimal("2")
        assert AsientoContable.objects.filter(
            id_empresa=empresa_a, nombre_modelo_origen="DevolucionVenta"
        ).count() == 0
