"""
Lógica de negocio del ciclo de ventas.

Flujo correcto (R-CODE-11 en emitir_factura_fiscal):

  obtener_precio()        → resuelve precio de un producto según lista del contacto o Lista 1
  confirmar_pedido()      → APROBADO + reserva cantidad_comprometida (sin mover stock físico)
  entregar_nota_venta()   → ENTREGADA + DESPACHO_VENTA (mueve stock físico, libera reserva)
                            + genera CuentaPorCobrar si no existe
  emitir_factura_fiscal() → EMITIDA + AsientoContable automático (R-CODE-11)
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.contabilidad.services import AsientoError, MapeoContableNoEncontrado, generar_asiento
from apps.core.services import FlujoError, verificar_paso_flujo  # noqa: F401 — re-exported for callers
from apps.inventario.services import (
    MovimientoInvalidoError,
    ReservaInsuficienteError,
    StockInsuficienteError,
    liberar_reserva,
    registrar_movimiento,
    reservar_stock,
)


# ── obtener_precio (M4) ───────────────────────────────────────────────────────


def obtener_precio(producto, empresa, contacto=None, fecha: date | None = None) -> Decimal:
    """
    Resuelve el precio de un producto para un contacto/empresa en una fecha.

    Prioridad:
      1. Lista asignada al contacto (contacto.lista_precio), si existe y tiene el producto.
      2. Lista de referencia de la empresa (es_referencia=True), si tiene el producto.
      3. precio_venta_sugerido del producto.

    Args:
        producto:  Instancia de inventario.Producto.
        empresa:   Instancia de core.Empresa.
        contacto:  Instancia de core.Contacto (opcional). Si es None, usa Lista 1 directamente.
        fecha:     Fecha de vigencia. Si None, usa hoy.

    Returns:
        Decimal con el precio resuelto.
    """
    from apps.ventas.models import DetallePrecio

    hoy = fecha or date.today()

    def _precio_en_lista(lista_precio):
        qs = DetallePrecio.objects.filter(
            id_lista=lista_precio,
            id_producto=producto,
            activo=True,
        ).filter(
            models.Q(vigente_desde__isnull=True) | models.Q(vigente_desde__lte=hoy)
        ).filter(
            models.Q(vigente_hasta__isnull=True) | models.Q(vigente_hasta__gte=hoy)
        )
        dp = qs.first()
        return dp.precio if dp else None

    # 1. Lista del contacto
    if contacto is not None:
        lista_contacto = getattr(contacto, "lista_precio", None)
        if lista_contacto:
            precio = _precio_en_lista(lista_contacto)
            if precio is not None:
                return precio

    # 2. Lista de referencia (Lista 1)
    from apps.ventas.models import ListaPrecio

    lista_ref = ListaPrecio.objects.filter(id_empresa=empresa, es_referencia=True, activo=True).first()
    if lista_ref:
        precio = _precio_en_lista(lista_ref)
        if precio is not None:
            return precio

    # 3. Fallback: precio sugerido del producto
    return Decimal(str(producto.precio_venta_sugerido))


# ── Excepciones de dominio ────────────────────────────────────────────────────


class VentaError(Exception):
    pass


# Alias para compatibilidad con código existente
PedidoConfirmacionError = VentaError


# ── confirmar_pedido ──────────────────────────────────────────────────────────


@transaction.atomic
def confirmar_pedido(pedido, almacen, usuario, generar_cxc: bool = None) -> dict:
    """
    Aprueba el pedido y reserva stock (cantidad_comprometida).
    NO crea MovimientoInventario — el stock físico sale en entregar_nota_venta().

    Args:
        pedido:      Instancia Pedido en estado PENDIENTE o ENVIADO.
        almacen:     Instancia Almacen de donde se despachará.
        usuario:     Instancia Usuarios que confirma.
        generar_cxc: None = auto (sigue tipo_cliente); True/False = forzar.

    Returns:
        {"reservas": [StockActual, ...], "cxc": CuentaPorCobrar | None}
    """
    if pedido.estado not in ("PENDIENTE", "ENVIADO"):
        raise VentaError(
            f"Solo se confirman pedidos PENDIENTE o ENVIADO. Estado actual: {pedido.estado}"
        )

    # M6: verificar que la COTIZACION previa fue completada si está configurada como obligatoria.
    cotizacion_cumplida = hasattr(pedido, "id_cotizacion_id") and pedido.id_cotizacion_id is not None
    verificar_paso_flujo(pedido.id_empresa, "VENTAS", "COTIZACION", cotizacion_cumplida)

    detalles = list(pedido.detalles.select_related("id_producto"))
    if not detalles:
        raise VentaError("El pedido no tiene líneas de detalle.")

    reservas = []
    for detalle in detalles:
        try:
            stock = reservar_stock(
                empresa=pedido.id_empresa,
                producto=detalle.id_producto,
                variante=None,
                almacen=almacen,
                cantidad=detalle.cantidad,
            )
        except StockInsuficienteError as exc:
            raise VentaError(str(exc)) from exc
        reservas.append(stock)

        # Sprint 0.H: crear MovimientoInventario(tipo=RESERVA_VENTA) como audit trail.
        # No altera cantidad_disponible — solo registra que el stock fue comprometido.
        try:
            registrar_movimiento(
                empresa=pedido.id_empresa,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="RESERVA_VENTA",
                producto=detalle.id_producto,
                cantidad=detalle.cantidad,
                documento_origen_id=pedido.id_pedido,
                nombre_modelo_origen="Pedido",
                usuario=usuario,
                observaciones=f"Reserva pedido {pedido.numero_pedido}",
            )
        except Exception:  # noqa: BLE001
            # La reserva de stock ya se hizo; el movimiento de audit es best-effort.
            pass

    pedido.estado = "APROBADO"
    pedido.save(update_fields=["estado"])

    cxc = None
    cliente = pedido.id_cliente
    debe_generar = generar_cxc if generar_cxc is not None else (cliente.tipo_cliente == "CREDITO")

    if debe_generar:
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        subtotal = sum(d.subtotal for d in detalles)
        dias = cliente.dias_credito or 30
        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=pedido.id_empresa,
            monto=subtotal,
            fecha_emision=timezone.now().date(),
            fecha_vencimiento=timezone.now().date() + timedelta(days=dias),
            estado="pendiente",
            descripcion=f"Pedido {pedido.numero_pedido}",
        )

    from apps.core.events import VentasEvents, publish

    publish(
        event_type=VentasEvents.PEDIDO_CONFIRMADO,
        tenant_id=str(pedido.id_empresa_id),
        payload={
            "pedido_id": str(pedido.id_pedido),
            "numero_pedido": pedido.numero_pedido,
            "cliente_id": str(pedido.id_cliente_id),
            "cxc_id": str(cxc.pk) if cxc else None,
        },
        actor_id=str(usuario.pk),
    )

    # Notificación in-app al vendedor que confirmó el pedido
    try:
        from apps.notificaciones.services import emitir_notificacion
        emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            pedido.id_empresa,
            usuario,
            {
                "numero_pedido": pedido.numero_pedido,
                "nombre_cliente": str(pedido.id_cliente),
            },
            url_accion=f"/ventas/pedidos/{pedido.id_pedido}/",
        )
    except Exception:  # noqa: BLE001
        pass  # La notificación es best-effort; no bloquea el flujo de venta

    return {"reservas": reservas, "cxc": cxc}


# ── entregar_nota_venta ───────────────────────────────────────────────────────


@transaction.atomic
def entregar_nota_venta(nota_venta, almacen, usuario) -> dict:
    """
    Despacha la NotaVenta: mueve stock físico, libera reservas, genera CxC si no existe.

    Precondiciones:
      - nota_venta.estado == 'BORRADOR'
      - El Pedido origen (si existe) debe estar en estado APROBADO.

    Returns:
        {"movimientos": [MovimientoInventario, ...], "cxc": CuentaPorCobrar | None}
    """
    if nota_venta.estado != "BORRADOR":
        raise VentaError(
            f"Solo se entregan notas en estado BORRADOR. Estado actual: {nota_venta.estado}"
        )

    # M6: verificar que el PEDIDO previo fue completado si está configurado como obligatorio.
    pedido = getattr(nota_venta, "id_pedido_origen", None)
    pedido_cumplido = pedido is not None and pedido.estado == "APROBADO"
    verificar_paso_flujo(nota_venta.id_empresa, "VENTAS", "PEDIDO", pedido_cumplido)

    if pedido and pedido.estado != "APROBADO":
        raise VentaError(
            f"El pedido origen debe estar APROBADO para poder entregar. Estado: {pedido.estado}"
        )

    detalles = list(nota_venta.detalles.select_related("id_producto"))
    if not detalles:
        raise VentaError("La nota de venta no tiene líneas de detalle.")

    movimientos = []
    for detalle in detalles:
        # Liberar reserva creada en confirmar_pedido (best-effort: puede no existir si
        # la venta fue directa sin pedido previo)
        try:
            liberar_reserva(
                empresa=nota_venta.id_empresa,
                producto=detalle.id_producto,
                variante=None,
                almacen=almacen,
                cantidad=detalle.cantidad,
            )
        except (ReservaInsuficienteError, Exception):
            pass  # Sin pedido previo no hay reserva que liberar

        try:
            mov = registrar_movimiento(
                empresa=nota_venta.id_empresa,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="DESPACHO_VENTA",
                producto=detalle.id_producto,
                cantidad=detalle.cantidad,
                almacen_origen=almacen,
                documento_origen_id=nota_venta.id_nota_venta,
                nombre_modelo_origen="NotaVenta",
                usuario=usuario,
                observaciones=f"Entrega nota {nota_venta.numero_nota}",
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise VentaError(str(exc)) from exc
        movimientos.append(mov)

    nota_venta.estado = "ENTREGADA"
    nota_venta.save(update_fields=["estado"])

    # Generar CxC si no viene de un pedido que ya la creó
    cxc = None
    tiene_cxc_de_pedido = pedido is not None and getattr(pedido, "id_cliente", None)
    if not tiene_cxc_de_pedido:
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = nota_venta.id_cliente
        subtotal = sum(d.subtotal for d in detalles)
        dias = getattr(cliente, "dias_credito", None) or 30
        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=nota_venta.id_empresa,
            monto=subtotal,
            fecha_emision=timezone.now().date(),
            fecha_vencimiento=timezone.now().date() + timedelta(days=dias),
            estado="pendiente",
            descripcion=f"Nota de venta {nota_venta.numero_nota}",
        )

    return {"movimientos": movimientos, "cxc": cxc}


# ── confirmar_nota_venta ──────────────────────────────────────────────────────


@transaction.atomic
def confirmar_nota_venta(nota_venta, almacen, usuario) -> dict:
    """
    Entrega la NotaVenta y genera el asiento contable NOTA_VENTA (R-CODE-11 — CTF-001).

    El asiento registra:
      DEBE  → Cuentas por Cobrar (CxC)
      HABER → Ingresos por Ventas

    El mapeo debe existir en Contabilidad → MapeoContable (tipo_asiento='NOTA_VENTA').
    Si no existe, la entrega sigue adelante (best-effort) pero el asiento no se genera;
    se adjunta 'asiento_error' en el resultado para trazabilidad.

    Args:
        nota_venta: instancia NotaVenta en estado BORRADOR
        almacen:    almacén de despacho
        usuario:    usuario que ejecuta la acción

    Returns:
        {"movimientos": [...], "cxc": ..., "asiento": AsientoContable | None, "asiento_error": str | None}
    """
    resultado = entregar_nota_venta(nota_venta, almacen, usuario)

    asiento = None
    asiento_error = None
    try:
        detalles = list(nota_venta.detalles.all())
        subtotal = sum(d.subtotal for d in detalles)
        asiento = generar_asiento(
            "NOTA_VENTA",
            nota_venta,
            nota_venta.id_empresa,
            monto=subtotal,
        )
    except MapeoContableNoEncontrado as exc:
        # El mapeo es opcional en ambientes sin contabilidad configurada
        asiento_error = str(exc)
    except AsientoError as exc:
        asiento_error = str(exc)

    resultado["asiento"] = asiento
    resultado["asiento_error"] = asiento_error
    return resultado


# ── emitir_factura_fiscal ─────────────────────────────────────────────────────


@transaction.atomic
def emitir_factura_fiscal(nota_venta, numero_control: str = None, numero_factura: str = None, moneda=None) -> dict:
    """
    Crea la FacturaFiscal desde la NotaVenta y genera el asiento contable (R-CODE-11).

    Precondiciones:
      - nota_venta.estado == 'ENTREGADA'

    Args:
        nota_venta: instancia NotaVenta en estado ENTREGADA
        numero_control: opcional — si None, se genera automáticamente
        numero_factura: opcional — si None, se genera automáticamente
        moneda: instancia Moneda (requerida si no hay moneda en la nota)

    Returns:
        {"factura": FacturaFiscal, "asiento": AsientoContable}
    """
    from apps.fiscal.services import calcular_impuestos, siguiente_numero
    from apps.ventas.models import FacturaFiscal

    if nota_venta.estado != "ENTREGADA":
        raise VentaError(
            f"Solo se facturan notas en estado ENTREGADA. Estado actual: {nota_venta.estado}"
        )

    empresa = nota_venta.id_empresa

    # Auto-generate correlative numbers if not provided
    if numero_factura is None:
        numero_factura = siguiente_numero(empresa, "FACTURA")
    if numero_control is None:
        numero_control = siguiente_numero(empresa, "NOTA_ENTREGA")

    # Resolve moneda — fall back to empresa base currency
    if moneda is None:
        moneda = getattr(empresa, "id_moneda_base", None)

    detalles = list(nota_venta.detalles.select_related("id_producto"))
    subtotal = sum(d.subtotal for d in detalles)

    # Use calcular_impuestos for proper IVA/IGTF computation
    impuestos = calcular_impuestos(subtotal, empresa, moneda)
    monto_iva = impuestos["monto_iva"]
    monto_igtf = impuestos["monto_igtf"]
    total = impuestos["total"]

    factura = FacturaFiscal.objects.create(
        id_empresa=empresa,
        id_cliente=nota_venta.id_cliente,
        id_nota_venta_origen=nota_venta,
        numero_control=numero_control,
        numero_factura=numero_factura,
        fecha_emision=timezone.now().date(),
        base_imponible=subtotal,
        monto_iva=monto_iva,
        monto_igtf=monto_igtf,
        monto_total=total,
        id_moneda=moneda,
        estado="EMITIDA",
    )

    try:
        asiento = generar_asiento("FACTURA_VENTA", factura, factura.id_empresa)
    except AsientoError as exc:
        raise VentaError(f"Error generando asiento contable: {exc}") from exc

    # CTF-001: asiento separado para el IVA (si el monto de IVA es positivo)
    asiento_iva = None
    asiento_iva_error = None
    if monto_iva > Decimal("0"):
        try:
            asiento_iva = generar_asiento(
                "FACTURA_VENTA_IVA",
                factura,
                factura.id_empresa,
                monto=monto_iva,
            )
        except MapeoContableNoEncontrado as exc:
            # El mapeo IVA es opcional; no bloquea la emisión de la factura
            asiento_iva_error = str(exc)
        except AsientoError as exc:
            asiento_iva_error = str(exc)

    # State transition happens after the asiento succeeds — if asiento fails the
    # entire @transaction.atomic rolls back, so nota_venta never reaches FACTURADA.
    nota_venta.convertido_a_factura = True
    nota_venta.id_factura_resultante = factura
    nota_venta.estado = "FACTURADA"
    nota_venta.save(update_fields=["convertido_a_factura", "id_factura_resultante", "estado"])

    # GAP-01: Create CuentaPorCobrar for the full invoice total
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from datetime import timedelta

    cliente = nota_venta.id_cliente
    dias_credito = getattr(cliente, "dias_credito", None) or 30
    fecha_emision = factura.fecha_emision
    cxc = CuentaPorCobrar.objects.create(
        cliente=cliente,
        empresa=empresa,
        monto=total,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_emision + timedelta(days=dias_credito),
        estado="pendiente",
        referencia_externa=factura.numero_factura,
        tipo_operacion="FACTURA_VENTA",
        descripcion=f"Factura Fiscal {factura.numero_factura}",
        documento_json={
            "id_factura": str(factura.id_factura),
            "base_imponible": str(subtotal),
            "monto_iva": str(monto_iva),
            "monto_igtf": str(monto_igtf),
            "monto_total": str(total),
        },
    )

    return {
        "factura": factura,
        "asiento": asiento,
        "asiento_iva": asiento_iva,
        "asiento_iva_error": asiento_iva_error,
        "cxc": cxc,
    }
