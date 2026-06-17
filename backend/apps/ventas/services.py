"""
Lógica de negocio del ciclo de ventas.

Flujo correcto (R-CODE-11 en emitir_factura_fiscal):

  obtener_precio()        → resuelve precio de un producto según lista del contacto o Lista 1
  confirmar_pedido()      → APROBADO + reserva cantidad_comprometida (sin mover stock físico)
                            + CuentaPorCobrar del flujo si el cliente es CREDITO
  entregar_nota_venta()   → ENTREGADA + DESPACHO_VENTA (mueve stock físico, libera reserva)
                            + genera CuentaPorCobrar si el flujo aún no tiene una
  emitir_factura_fiscal() → EMITIDA + AsientoContable automático (R-CODE-11)
                            + REUTILIZA la CxC del flujo (monto → total con impuestos)

BUG-A4: existe **una sola CuentaPorCobrar por flujo de venta**, vinculada vía
documento_json (id_pedido / id_nota_venta / id_factura). Nace en confirmar_pedido
(crédito) o en entregar_nota_venta (contado o venta directa) y al facturar se
actualiza al total fiscal — nunca se crea una segunda.
"""

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

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

    hoy = fecha or timezone.localdate()

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
        except (StockInsuficienteError, MovimientoInvalidoError, ReservaInsuficienteError) as exc:
            # El movimiento de auditoría es best-effort (la reserva ya se hizo),
            # pero NO se traga en silencio: M-BUG-3.
            logger.warning(
                "confirmar_pedido: no se registró movimiento de auditoría para pedido %s: %s",
                pedido.id_pedido, exc,
            )

    pedido.estado = "APROBADO"
    pedido.save(update_fields=["estado"])

    cxc = None
    cliente = pedido.id_cliente
    debe_generar = generar_cxc if generar_cxc is not None else (cliente.tipo_cliente == "CREDITO")

    if debe_generar:
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        subtotal = sum(d.subtotal for d in detalles)
        dias = cliente.dias_credito or 30
        # BUG-A4: documento_json["id_pedido"] vincula la CxC al pedido para que
        # entregar_nota_venta no cree una segunda y emitir_factura_fiscal la
        # reutilice (actualizando el monto al total con impuestos).
        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=pedido.id_empresa,
            monto=subtotal,
            fecha_emision=timezone.localdate(),
            fecha_vencimiento=timezone.localdate() + timedelta(days=dias),
            estado="pendiente",
            referencia_externa=pedido.numero_pedido,
            tipo_operacion="PEDIDO_VENTA",
            descripcion=f"Pedido {pedido.numero_pedido}",
            documento_json={"id_pedido": str(pedido.id_pedido)},
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


# ── convertir_pedido_a_nota_venta ─────────────────────────────────────────────


@transaction.atomic
def convertir_pedido_a_nota_venta(pedido, usuario=None):
    """
    Crea la NotaVenta (BORRADOR) a partir de un Pedido APROBADO, copiando sus
    líneas de detalle, y marca el pedido como convertido.

    Gap E2E (PR #76): el botón "Convertir a Nota Venta" del frontend llamaba a
    un endpoint inexistente. Este service respalda ese endpoint.

    Args:
        pedido:  Instancia Pedido en estado APROBADO y no convertido aún.
        usuario: Usuario que ejecuta la conversión (auditoría/eventos).

    Returns:
        NotaVenta creada (estado BORRADOR, lista para entregar/facturar).
    """
    from apps.fiscal.services import siguiente_numero
    from apps.ventas.models import DetalleNotaVenta, NotaVenta, Pedido

    # Lock de fila: dos clics simultáneos no deben crear dos notas (doble submit).
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)

    if pedido.convertido_a_nota_venta:
        raise VentaError("El pedido ya fue convertido a nota de venta.")
    if pedido.estado != "APROBADO":
        raise VentaError(
            f"Solo se convierten pedidos APROBADOS. Estado actual: {pedido.estado}"
        )

    detalles = list(pedido.detalles.select_related("id_producto"))
    if not detalles:
        raise VentaError("El pedido no tiene líneas de detalle.")

    numero_nota = siguiente_numero(pedido.id_empresa, "NOTA_VENTA")
    nota = NotaVenta.objects.create(
        id_empresa=pedido.id_empresa,
        id_cliente=pedido.id_cliente,
        id_pedido_origen=pedido,
        # 1.G: el vendedor del pedido viaja a la nota — es la base del devengo
        # de comisión al entregar.
        id_vendedor=pedido.id_vendedor,
        numero_nota=numero_nota,
        fecha_nota=timezone.localdate(),
        estado="BORRADOR",
        observaciones=pedido.observaciones,
    )
    DetalleNotaVenta.objects.bulk_create(
        [
            DetalleNotaVenta(
                id_nota_venta=nota,
                id_producto=detalle.id_producto,
                cantidad=detalle.cantidad,
                precio_unitario=detalle.precio_unitario,
                subtotal=detalle.subtotal,
                observaciones=detalle.observaciones,
            )
            for detalle in detalles
        ]
    )

    pedido.convertido_a_nota_venta = True
    pedido.id_nota_venta_resultante = nota
    pedido.save(update_fields=["convertido_a_nota_venta", "id_nota_venta_resultante"])

    return nota


# ── CxC del flujo de venta (BUG-A4) ───────────────────────────────────────────


def _buscar_cxc_flujo_venta(nota_venta, pedido=None, para_actualizar: bool = False):
    """
    Devuelve la CuentaPorCobrar ya creada para este flujo de venta (la del
    pedido en confirmar_pedido o la de la nota en entregar_nota_venta), o None.

    El vínculo es documento_json["id_pedido"] / documento_json["id_nota_venta"],
    siempre acotado a la empresa de la nota (multi-tenant).
    """
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar

    filtros = models.Q(documento_json__id_nota_venta=str(nota_venta.id_nota_venta))
    if pedido is not None:
        filtros |= models.Q(documento_json__id_pedido=str(pedido.id_pedido))

    qs = (
        CuentaPorCobrar.objects.filter(empresa=nota_venta.id_empresa)
        .filter(filtros)
        .order_by("pk")
    )
    if para_actualizar:
        qs = qs.select_for_update()
    return qs.first()


# ── entregar_nota_venta ───────────────────────────────────────────────────────


@transaction.atomic
def entregar_nota_venta(nota_venta, almacen, usuario) -> dict:
    """
    Despacha la NotaVenta: mueve stock físico, libera reservas, genera CxC si
    el flujo aún no tiene una.

    BUG-A4 — decisión de flujo de CxC: la entrega despacha mercancía, así que el
    derecho de cobro debe quedar registrado SIEMPRE. Si el pedido origen ya creó
    la CxC del flujo (cliente CREDITO en confirmar_pedido) se reutiliza esa; si
    no existe (venta CONTADO con pedido, o venta directa sin pedido) se crea
    aquí por el subtotal. Antes solo se verificaba que el pedido tuviera cliente
    (siempre cierto), por lo que la venta CONTADO con pedido entregada y no
    facturada quedaba sin CxC.

    Precondiciones:
      - nota_venta.estado == 'BORRADOR'
      - El Pedido origen (si existe) debe estar en estado APROBADO.

    Returns:
        {"movimientos": [MovimientoInventario, ...], "cxc": CuentaPorCobrar}
        (cxc es la del flujo: la preexistente del pedido o la recién creada)
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
        except ReservaInsuficienteError:
            # Sin pedido previo no hay reserva que liberar — caso esperado.
            # H-BUG-4: NO capturar Exception genérico; un deadlock u otro error
            # de transacción debe propagar para que @transaction.atomic revierta.
            logger.debug(
                "entregar_nota_venta: sin reserva previa para producto %s (venta directa).",
                detalle.id_producto,
            )

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

    # BUG-A4: generar la CxC del flujo solo si NO existe ya una (la del pedido,
    # creada en confirmar_pedido para clientes CREDITO). Antes se asumía "ya
    # tiene CxC" con solo verificar que el pedido tenía cliente, dejando la
    # venta CONTADO con pedido sin CxC.
    cxc = _buscar_cxc_flujo_venta(nota_venta, pedido)
    if cxc is None:
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = nota_venta.id_cliente
        subtotal = sum(d.subtotal for d in detalles)
        dias = getattr(cliente, "dias_credito", None) or 30
        documento_json = {"id_nota_venta": str(nota_venta.id_nota_venta)}
        if pedido is not None:
            documento_json["id_pedido"] = str(pedido.id_pedido)
        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=nota_venta.id_empresa,
            monto=subtotal,
            fecha_emision=timezone.localdate(),
            fecha_vencimiento=timezone.localdate() + timedelta(days=dias),
            estado="pendiente",
            referencia_externa=nota_venta.numero_nota,
            tipo_operacion="NOTA_VENTA",
            descripcion=f"Nota de venta {nota_venta.numero_nota}",
            documento_json=documento_json,
        )

    # 1.G — Comisiones: la entrega es el punto donde la venta es firme (sale
    # mercancía y nace el derecho de cobro), así que aquí se devenga la comisión
    # del vendedor, DENTRO de la misma transacción (si algo falla, todo revierte).
    # Cubre ventas con y sin factura fiscal sin riesgo de doble devengo (la
    # factura siempre deriva de una nota ya ENTREGADA).
    comision = devengar_comision_venta(nota_venta)

    return {"movimientos": movimientos, "cxc": cxc, "comision": comision}


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
    except (MapeoContableNoEncontrado, AsientoError) as exc:
        # H-BUG-1: si la empresa exige contabilidad, la falta de asiento es un
        # error duro (la @transaction.atomic revierte). Para empresas sin
        # contabilidad (bodega informal, R-PROD-3) la operación procede sin asiento.
        if getattr(nota_venta.id_empresa, "contabilidad_activa", False):
            raise VentaError(
                f"Configure el Mapeo Contable antes de confirmar (contabilidad activa): {exc}"
            ) from exc
        asiento_error = str(exc)

    resultado["asiento"] = asiento
    resultado["asiento_error"] = asiento_error
    return resultado


# ── emitir_factura_fiscal ─────────────────────────────────────────────────────


@transaction.atomic
def emitir_factura_fiscal(nota_venta, numero_control: str = None, numero_factura: str = None, moneda=None) -> dict:
    """
    Crea la FacturaFiscal desde la NotaVenta y genera el asiento contable (R-CODE-11).

    BUG-A4 — CxC: si el flujo ya tiene CuentaPorCobrar (creada en confirmar_pedido
    o entregar_nota_venta) se reutiliza, actualizando el monto al total fiscal;
    NUNCA se crea una segunda. Solo se crea CxC nueva si el flujo no tiene una.

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
        fecha_emision=timezone.localdate(),
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
        # H-BUG-2: si la empresa es contribuyente de IVA, el asiento de IVA es
        # OBLIGATORIO. Ninguna factura SENIAT puede quedar "EMITIDA" sin su
        # asiento de IVA descuadrando la contabilidad. Para no contribuyentes
        # (o sin configuración fiscal) se mantiene best-effort.
        from apps.fiscal.models import ConfiguracionFiscalEmpresa

        config_fiscal = ConfiguracionFiscalEmpresa.objects.filter(id_empresa=factura.id_empresa).first()
        iva_obligatorio = bool(config_fiscal and config_fiscal.contribuyente_iva)
        try:
            asiento_iva = generar_asiento(
                "FACTURA_VENTA_IVA",
                factura,
                factura.id_empresa,
                monto=monto_iva,
            )
        except (MapeoContableNoEncontrado, AsientoError) as exc:
            if iva_obligatorio:
                raise VentaError(
                    "Configure el Mapeo Contable de IVA antes de emitir facturas "
                    f"como contribuyente: {exc}"
                ) from exc
            asiento_iva_error = str(exc)

    # State transition happens after the asiento succeeds — if asiento fails the
    # entire @transaction.atomic rolls back, so nota_venta never reaches FACTURADA.
    nota_venta.convertido_a_factura = True
    nota_venta.id_factura_resultante = factura
    nota_venta.estado = "FACTURADA"
    nota_venta.save(update_fields=["convertido_a_factura", "id_factura_resultante", "estado"])

    # GAP-01 + BUG-A4: una sola CuentaPorCobrar por el total del flujo.
    # Si el pedido (confirmar_pedido) o la entrega (entregar_nota_venta) ya
    # crearon la CxC del flujo, se REUTILIZA actualizando el monto al total
    # fiscal (base + IVA + IGTF) — así se preservan los abonos ya registrados
    # y el cliente nunca aparece debiendo dos veces. Solo si no existe ninguna
    # (datos previos al fix, o nota ENTREGADA creada fuera del flujo) se crea.
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from datetime import timedelta

    cliente = nota_venta.id_cliente
    dias_credito = getattr(cliente, "dias_credito", None) or 30
    fecha_emision = factura.fecha_emision
    documento_json_cxc = {
        "id_factura": str(factura.id_factura),
        "id_nota_venta": str(nota_venta.id_nota_venta),
        "base_imponible": str(subtotal),
        "monto_iva": str(monto_iva),
        "monto_igtf": str(monto_igtf),
        "monto_total": str(total),
    }
    pedido_origen = getattr(nota_venta, "id_pedido_origen", None)
    if pedido_origen is not None:
        documento_json_cxc["id_pedido"] = str(pedido_origen.id_pedido)

    cxc = _buscar_cxc_flujo_venta(nota_venta, pedido_origen, para_actualizar=True)
    if cxc is not None:
        cxc.monto = total
        cxc.fecha_vencimiento = fecha_emision + timedelta(days=dias_credito)
        cxc.referencia_externa = factura.numero_factura
        cxc.tipo_operacion = "FACTURA_VENTA"
        cxc.descripcion = f"Factura Fiscal {factura.numero_factura}"
        cxc.documento_json = {**(cxc.documento_json or {}), **documento_json_cxc}
        # Recalcular el estado contra el nuevo total (los abonos previos cuentan)
        abonado = cxc.abonos.aggregate(s=models.Sum("monto"))["s"] or Decimal("0")
        if abonado >= cxc.monto:
            cxc.estado = "pagada"
        elif abonado > Decimal("0"):
            cxc.estado = "parcial"
        else:
            cxc.estado = "pendiente"
        cxc.save(
            update_fields=[
                "monto",
                "fecha_vencimiento",
                "referencia_externa",
                "tipo_operacion",
                "descripcion",
                "documento_json",
                "estado",
            ]
        )
    else:
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
            documento_json=documento_json_cxc,
        )

    return {
        "factura": factura,
        "asiento": asiento,
        "asiento_iva": asiento_iva,
        "asiento_iva_error": asiento_iva_error,
        "cxc": cxc,
    }


# ── Comisiones de vendedores (1.G) ────────────────────────────────────────────

#: Cuantización de montos de comisión: 4 decimales (convención monetaria del
#: proyecto) con ROUND_HALF_UP (default comercial de omni-decimal-money).
_CUATRO_DECIMALES = Decimal("0.0001")
_CIEN = Decimal("100")


def _esquema_comision_vigente(empresa, vendedor, fecha: date):
    """
    Esquema de comisión aplicable a un vendedor de la empresa en una fecha:
    activo y con la fecha dentro de la vigencia (límites NULL = abiertos).
    Si hay varios vigentes, gana el de ``vigente_desde`` más reciente (regla
    determinística, mismo espíritu que las listas de precio).
    """
    from apps.ventas.models import EsquemaComision

    return (
        EsquemaComision.objects.filter(id_empresa=empresa, vendedor=vendedor, activo=True)
        .filter(models.Q(vigente_desde__isnull=True) | models.Q(vigente_desde__lte=fecha))
        .filter(models.Q(vigente_hasta__isnull=True) | models.Q(vigente_hasta__gte=fecha))
        .order_by(models.F("vigente_desde").desc(nulls_last=True), "-fecha_creacion")
        .first()
    )


def devengar_comision_venta(nota_venta):
    """
    Registra la comisión devengada de la venta (NotaVenta recién ENTREGADA).

    Reglas:
      - Sin vendedor asignado o sin esquema vigente → no hay comisión (None);
        no es un error: la venta procede igual.
      - Base comisionable = subtotal de la nota (sin IVA/IGTF: las comisiones
        no se pagan sobre impuestos).
      - Porcentaje por línea: override de la categoría del producto si el
        esquema lo define; si no, el porcentaje base del esquema.
      - Todo en Decimal, cuantizado a 4 decimales ROUND_HALF_UP (R-CODE-4).
      - El OneToOne nota↔comisión hace el devengo idempotente: si ya existe,
        se devuelve la existente sin recalcular.

    Debe invocarse DENTRO de la transacción de la entrega (R-CODE-11): si el
    INSERT de la comisión falla, la entrega completa revierte.
    """
    from apps.ventas.models import ComisionVenta

    vendedor = nota_venta.id_vendedor
    if vendedor is None:
        return None

    existente = ComisionVenta.objects.filter(nota_venta=nota_venta).first()
    if existente is not None:
        return existente

    fecha = nota_venta.fecha_nota or timezone.localdate()
    esquema = _esquema_comision_vigente(nota_venta.id_empresa, vendedor, fecha)
    if esquema is None:
        logger.info(
            "devengar_comision_venta: nota %s con vendedor %s sin esquema vigente; no se devenga.",
            nota_venta.id_nota_venta,
            vendedor.pk,
        )
        return None

    overrides = {
        o.categoria_id: o.porcentaje for o in esquema.overrides_categoria.all()
    }

    base = Decimal("0")
    monto = Decimal("0")
    detalle = []
    for linea in nota_venta.detalles.select_related("id_producto"):
        porcentaje = overrides.get(linea.id_producto.id_categoria_id, esquema.porcentaje_base)
        subtotal = linea.subtotal
        monto_linea = (subtotal * porcentaje / _CIEN).quantize(
            _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
        )
        base += subtotal
        monto += monto_linea
        detalle.append(
            {
                "id_producto": str(linea.id_producto_id),
                "subtotal": str(subtotal),
                "porcentaje": str(porcentaje),
                "monto": str(monto_linea),
            }
        )

    return ComisionVenta.objects.create(
        id_empresa=nota_venta.id_empresa,
        vendedor=vendedor,
        nota_venta=nota_venta,
        esquema=esquema,
        base_comisionable=base,
        monto=monto,
        id_moneda=getattr(nota_venta.id_empresa, "id_moneda_base", None),
        estado="DEVENGADA",
        fecha_devengo=fecha,
        detalle_json=detalle,
    )


def anular_comision_de_nota_venta(nota_venta):
    """
    Anula la comisión asociada a una NotaVenta que se está anulando, en la
    MISMA transacción que el cambio de estado de la nota (el caller garantiza
    el ``transaction.atomic``).

    - Sin comisión o ya ANULADA → no-op (None / la existente).
    - LIQUIDADA → VentaError: la comisión ya se pagó al vendedor; la venta no
      puede anularse "en silencio". El flujo correcto es devolución / nota de
      crédito (resto de 1.G).
    """
    from apps.ventas.models import ComisionVenta

    comision = (
        ComisionVenta.objects.select_for_update().filter(nota_venta=nota_venta).first()
    )
    if comision is None or comision.estado == "ANULADA":
        return comision
    if comision.estado == "LIQUIDADA":
        raise VentaError(
            "La comisión de esta venta ya fue liquidada al vendedor; no se puede "
            "anular la nota. Registre una devolución o nota de crédito."
        )
    comision.estado = "ANULADA"
    comision.save(update_fields=["estado"])
    return comision


@transaction.atomic
def liquidar_comisiones(empresas, vendedor, desde: date, hasta: date, usuario):
    """
    Marca como LIQUIDADAS todas las comisiones DEVENGADAS de un vendedor en un
    período (``fecha_devengo`` en [desde, hasta]), acotado a ``empresas``
    (las visibles del usuario — R-CODE-1).

    Con ``select_for_update``: dos liquidaciones concurrentes del mismo rango
    no duplican el pago (la segunda ve 0 pendientes).

    Returns:
        {"liquidadas": int, "monto_total": Decimal}
    """
    from apps.ventas.models import ComisionVenta

    if desde > hasta:
        raise VentaError("El rango de fechas es inválido: 'desde' es posterior a 'hasta'.")

    pendientes = list(
        ComisionVenta.objects.select_for_update()
        .filter(
            id_empresa__in=empresas,
            vendedor=vendedor,
            estado="DEVENGADA",
            fecha_devengo__gte=desde,
            fecha_devengo__lte=hasta,
        )
    )
    hoy = timezone.localdate()
    total = Decimal("0")
    for comision in pendientes:
        comision.estado = "LIQUIDADA"
        comision.fecha_liquidacion = hoy
        comision.liquidada_por = usuario
        total += comision.monto
    ComisionVenta.objects.bulk_update(
        pendientes, ["estado", "fecha_liquidacion", "liquidada_por"]
    )
    return {"liquidadas": len(pendientes), "monto_total": total}
