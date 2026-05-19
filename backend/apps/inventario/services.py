"""
Lógica de negocio para movimientos de inventario.

Expone:
  registrar_movimiento()   — crea un MovimientoInventario y actualiza StockActual
                             de forma atómica.
  StockInsuficienteError   — stock disponible menor al solicitado en una SALIDA.
  MovimientoInvalidoError  — datos inválidos (almacén faltante, mismo origen/destino, …).
"""

from decimal import Decimal

from django.db import transaction

from .models import MovimientoInventario, StockActual

# ── Clasificación de tipos de movimiento ─────────────────────────────────────

TIPOS_ENTRADA = frozenset({"ENTRADA", "RECEPCION_COMPRA"})
TIPOS_SALIDA = frozenset({"SALIDA", "DESPACHO_VENTA", "CONSUMO_PRODUCCION", "SALIDA_INTERNA"})
TIPOS_TRANSFERENCIA = frozenset({"TRANSFERENCIA"})
TIPOS_AJUSTE = frozenset({"AJUSTE"})

ALL_TIPOS = TIPOS_ENTRADA | TIPOS_SALIDA | TIPOS_TRANSFERENCIA | TIPOS_AJUSTE

# Salidas que REQUIEREN un documento origen válido (M5 — control de salidas)
TIPOS_SALIDA_CONTROLADA = frozenset({"SALIDA_INTERNA"})

# M5-T3: tipos que requieren documento de venta aprobado
TIPOS_DESPACHO_VENTA = frozenset({"DESPACHO_VENTA"})

# M5-T3: tipos de ajuste que requieren documento_origen_id como justificante
TIPOS_AJUSTE_CONTROLADO = frozenset({"AJUSTE"})


# ── Excepciones adicionales ───────────────────────────────────────────────────


class ReservaInsuficienteError(Exception):
    pass


# ── Excepciones de dominio ────────────────────────────────────────────────────


class StockInsuficienteError(Exception):
    pass


class MovimientoInvalidoError(Exception):
    pass


# ── Helpers internos ──────────────────────────────────────────────────────────


def _actualizar_stock(empresa, producto, variante, almacen, delta: Decimal) -> StockActual:
    """
    Aplica `delta` a StockActual.cantidad_disponible dentro de una transacción activa.
    Usa get_or_create + select_for_update para evitar race conditions.
    """
    stock, _ = StockActual.objects.get_or_create(
        id_producto=producto,
        id_variante=variante,
        id_almacen=almacen,
        defaults={"id_empresa": empresa, "cantidad_disponible": Decimal("0")},
    )
    # Lock the row for the rest of the transaction
    stock = StockActual.objects.select_for_update().get(pk=stock.pk)

    nuevo = stock.cantidad_disponible + delta
    if nuevo < 0:
        raise StockInsuficienteError(
            f"Stock insuficiente en '{almacen}'. "
            f"Disponible: {stock.cantidad_disponible}, solicitado: {abs(delta)}"
        )
    stock.cantidad_disponible = nuevo
    stock.save(update_fields=["cantidad_disponible", "fecha_ultima_actualizacion"])
    return stock


def delta_para_almacen(movimiento: MovimientoInventario, almacen_id) -> Decimal:
    """
    Calcula el delta de cantidad_disponible que produce `movimiento` sobre `almacen_id`.
    Retorna Decimal positivo (ingreso) o negativo (egreso) o cero (no afecta este almacén).
    """
    tipo = movimiento.tipo_movimiento
    str_id = str(almacen_id)
    origen = str(movimiento.id_almacen_origen_id) if movimiento.id_almacen_origen_id else None
    destino = str(movimiento.id_almacen_destino_id) if movimiento.id_almacen_destino_id else None

    if tipo in TIPOS_ENTRADA and destino == str_id:
        return movimiento.cantidad
    if tipo in TIPOS_SALIDA and origen == str_id:
        return -movimiento.cantidad
    if tipo in TIPOS_TRANSFERENCIA:
        if destino == str_id:
            return movimiento.cantidad
        if origen == str_id:
            return -movimiento.cantidad
    if tipo in TIPOS_AJUSTE and destino == str_id:
        return movimiento.cantidad  # signed (positive = entrada, negative = salida)
    return Decimal("0")


# ── Reservas de stock (sin movimiento de inventario) ─────────────────────────


@transaction.atomic
def reservar_stock(empresa, producto, variante, almacen, cantidad: Decimal) -> StockActual:
    """
    Incrementa cantidad_comprometida sin crear MovimientoInventario.
    Verifica que haya suficiente stock disponible no comprometido.
    Se usa en confirmar_pedido() — el stock sale físicamente sólo en la entrega.
    """
    cantidad = Decimal(str(cantidad))
    stock, _ = StockActual.objects.get_or_create(
        id_producto=producto,
        id_variante=variante,
        id_almacen=almacen,
        defaults={"id_empresa": empresa, "cantidad_disponible": Decimal("0")},
    )
    stock = StockActual.objects.select_for_update().get(pk=stock.pk)

    libre = stock.cantidad_disponible - stock.cantidad_comprometida
    if libre < cantidad:
        raise StockInsuficienteError(
            f"Stock libre insuficiente en '{almacen}' para '{producto}'. "
            f"Disponible: {stock.cantidad_disponible}, Comprometido: {stock.cantidad_comprometida}, "
            f"Libre: {libre}, Solicitado: {cantidad}"
        )
    stock.cantidad_comprometida += cantidad
    stock.save(update_fields=["cantidad_comprometida", "fecha_ultima_actualizacion"])
    return stock


@transaction.atomic
def liberar_reserva(empresa, producto, variante, almacen, cantidad: Decimal) -> StockActual:
    """
    Reduce cantidad_comprometida. Se usa en entregar_nota_venta() justo antes
    de crear el MovimientoInventario que descuenta cantidad_disponible.
    """
    cantidad = Decimal(str(cantidad))
    stock = StockActual.objects.select_for_update().get(
        id_producto=producto,
        id_variante=variante,
        id_almacen=almacen,
    )
    if stock.cantidad_comprometida < cantidad:
        raise ReservaInsuficienteError(
            f"Reserva insuficiente para liberar. Comprometido: {stock.cantidad_comprometida}, "
            f"Liberando: {cantidad}"
        )
    stock.cantidad_comprometida -= cantidad
    stock.save(update_fields=["cantidad_comprometida", "fecha_ultima_actualizacion"])
    return stock


# ── Función principal ─────────────────────────────────────────────────────────


@transaction.atomic
def registrar_movimiento(
    *,
    empresa,
    fecha_hora_movimiento,
    tipo_movimiento: str,
    producto,
    variante=None,
    cantidad,
    almacen_origen=None,
    almacen_destino=None,
    costo_unitario=None,
    documento_origen_id=None,
    nombre_modelo_origen=None,
    usuario,
    observaciones=None,
) -> MovimientoInventario:
    """
    Crea un MovimientoInventario y actualiza StockActual de forma atómica.

    Reglas de validación:
      ENTRADA / RECEPCION_COMPRA       → requiere almacen_destino
      SALIDA / DESPACHO_VENTA /
        CONSUMO_PRODUCCION             → requiere almacen_origen
      TRANSFERENCIA                    → requiere ambos; origen ≠ destino
      AJUSTE                           → requiere almacen_destino;
                                         cantidad puede ser negativa (reducción)
    """
    tipo = tipo_movimiento
    cantidad = Decimal(str(cantidad))

    # ── Validaciones de presencia de almacén ─────────────────────────────────
    if tipo in TIPOS_ENTRADA:
        if not almacen_destino:
            raise MovimientoInvalidoError(f"El tipo '{tipo}' requiere id_almacen_destino.")
    elif tipo in TIPOS_SALIDA:
        if not almacen_origen:
            raise MovimientoInvalidoError(f"El tipo '{tipo}' requiere id_almacen_origen.")
    elif tipo in TIPOS_TRANSFERENCIA:
        if not almacen_origen or not almacen_destino:
            raise MovimientoInvalidoError("TRANSFERENCIA requiere id_almacen_origen e id_almacen_destino.")
        if almacen_origen == almacen_destino:
            raise MovimientoInvalidoError("El almacén de origen y destino deben ser distintos.")
    elif tipo in TIPOS_AJUSTE:
        if not almacen_destino:
            raise MovimientoInvalidoError("AJUSTE requiere id_almacen_destino.")
    else:
        raise MovimientoInvalidoError(f"Tipo de movimiento desconocido: '{tipo}'.")

    if tipo not in TIPOS_AJUSTE and cantidad <= 0:
        raise MovimientoInvalidoError("La cantidad debe ser mayor a cero.")

    # ── Validar documento origen para salidas controladas (M5) ───────────────
    if tipo in TIPOS_SALIDA_CONTROLADA:
        if not documento_origen_id:
            raise MovimientoInvalidoError(
                f"El tipo '{tipo}' requiere un documento_origen_id (RequisicionInterna)."
            )
        from .models import RequisicionInterna

        try:
            req = RequisicionInterna.objects.get(id_requisicion=documento_origen_id, id_empresa=empresa)
        except RequisicionInterna.DoesNotExist:
            raise MovimientoInvalidoError(
                f"RequisicionInterna '{documento_origen_id}' no existe."
            )
        if req.estado != "APROBADA":
            raise MovimientoInvalidoError(
                f"La requisición debe estar APROBADA para despachar. Estado actual: {req.estado}"
            )

    # ── M5-T3: Validar documento de venta para DESPACHO_VENTA ────────────────
    if tipo in TIPOS_DESPACHO_VENTA:
        if not documento_origen_id:
            raise MovimientoInvalidoError(
                "DESPACHO_VENTA requiere un documento_origen_id (NotaVenta o FacturaFiscal)."
            )
        from apps.ventas.models import FacturaFiscal, NotaVenta

        nota = NotaVenta.objects.filter(id_nota_venta=documento_origen_id, id_empresa=empresa).first()
        factura = FacturaFiscal.objects.filter(id_factura=documento_origen_id, id_empresa=empresa).first()

        if not nota and not factura:
            raise MovimientoInvalidoError(
                f"El documento_origen_id '{documento_origen_id}' no corresponde a ninguna "
                "NotaVenta o FacturaFiscal activa en esta empresa."
            )

        # Validar estado del documento de venta
        if nota and nota.estado not in ("CONFIRMADA", "APROBADA", "PENDIENTE_DESPACHO"):
            raise MovimientoInvalidoError(
                f"La NotaVenta debe estar en estado CONFIRMADA / APROBADA / PENDIENTE_DESPACHO "
                f"para hacer un despacho. Estado actual: {nota.estado}"
            )
        if factura and factura.estado not in ("EMITIDA", "PENDIENTE_DESPACHO"):
            raise MovimientoInvalidoError(
                f"La FacturaFiscal debe estar en estado EMITIDA para hacer un despacho. "
                f"Estado actual: {factura.estado}"
            )

    # ── M5-T3: Advertencia para AJUSTE sin justificante ──────────────────────
    if tipo in TIPOS_AJUSTE_CONTROLADO and not documento_origen_id:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "AJUSTE de inventario registrado sin documento_origen_id. "
            "Se recomienda referenciar una autorización o justificante. "
            "Empresa=%s Producto=%s Cantidad=%s",
            empresa,
            producto,
            cantidad,
        )

    # ── Persistir movimiento ──────────────────────────────────────────────────
    movimiento = MovimientoInventario.objects.create(
        id_empresa=empresa,
        fecha_hora_movimiento=fecha_hora_movimiento,
        tipo_movimiento=tipo,
        id_producto=producto,
        id_variante=variante,
        cantidad=cantidad,
        id_almacen_origen=almacen_origen,
        id_almacen_destino=almacen_destino,
        costo_unitario_movimiento=costo_unitario,
        id_documento_origen=documento_origen_id,
        nombre_modelo_origen=nombre_modelo_origen,
        id_usuario_registro=usuario,
        observaciones=observaciones,
    )

    # ── Actualizar StockActual ────────────────────────────────────────────────
    if tipo in TIPOS_ENTRADA:
        _actualizar_stock(empresa, producto, variante, almacen_destino, cantidad)

    elif tipo in TIPOS_SALIDA:
        _actualizar_stock(empresa, producto, variante, almacen_origen, -cantidad)

    elif tipo in TIPOS_TRANSFERENCIA:
        _actualizar_stock(empresa, producto, variante, almacen_origen, -cantidad)
        _actualizar_stock(empresa, producto, variante, almacen_destino, cantidad)

    elif tipo in TIPOS_AJUSTE:
        _actualizar_stock(empresa, producto, variante, almacen_destino, cantidad)

    # ── M5-T4: Asiento contable para ajustes de inventario (R-CODE-11) ──────
    if tipo in TIPOS_AJUSTE and movimiento.monto_total > 0:
        try:
            from apps.contabilidad.services import MapeoContableNoEncontrado, generar_asiento
            generar_asiento("AJUSTE_INVENTARIO", movimiento, empresa)
        except MapeoContableNoEncontrado:
            # No hay mapeo contable configurado → el movimiento se registra igual,
            # pero sin asiento. El contador debe configurar el mapeo para activarlo.
            pass

    return movimiento


# ── despachar_requisicion_interna (M5) ───────────────────────────────────────


class RequisicionError(Exception):
    pass


@transaction.atomic
def aprobar_requisicion(requisicion, aprobado_por) -> None:
    """
    Aprueba una RequisicionInterna en estado BORRADOR.
    Solo cambia el estado; no mueve stock.
    """
    from datetime import date

    if requisicion.estado != "BORRADOR":
        raise RequisicionError(
            f"Solo se aprueban requisiciones en BORRADOR. Estado: {requisicion.estado}"
        )
    requisicion.estado = "APROBADA"
    requisicion.aprobado_por = aprobado_por
    requisicion.fecha_aprobacion = date.today()
    requisicion.save(update_fields=["estado", "aprobado_por", "fecha_aprobacion"])


@transaction.atomic
def despachar_requisicion_interna(requisicion, usuario) -> list:
    """
    Despacha una RequisicionInterna APROBADA:
      - Por cada línea crea un MovimientoInventario tipo SALIDA_INTERNA.
      - Actualiza cantidad_despachada en cada DetalleRequisicion.
      - Transiciona la requisición a DESPACHADA.

    Returns:
        Lista de MovimientoInventario creados.
    """
    from django.utils import timezone

    if requisicion.estado != "APROBADA":
        raise RequisicionError(
            f"Solo se despachan requisiciones APROBADAS. Estado: {requisicion.estado}"
        )

    detalles = list(requisicion.detalles.select_related("id_producto", "id_variante"))
    if not detalles:
        raise RequisicionError("La requisición no tiene líneas de detalle.")

    movimientos = []
    for detalle in detalles:
        try:
            mov = registrar_movimiento(
                empresa=requisicion.id_empresa,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="SALIDA_INTERNA",
                producto=detalle.id_producto,
                variante=detalle.id_variante,
                cantidad=detalle.cantidad_solicitada,
                almacen_origen=requisicion.id_almacen_origen,
                documento_origen_id=requisicion.id_requisicion,
                nombre_modelo_origen="RequisicionInterna",
                usuario=usuario,
                observaciones=f"Despacho requisición {requisicion.numero_requisicion}",
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise RequisicionError(str(exc)) from exc

        detalle.cantidad_despachada = detalle.cantidad_solicitada
        detalle.save(update_fields=["cantidad_despachada"])
        movimientos.append(mov)

    requisicion.estado = "DESPACHADA"
    requisicion.save(update_fields=["estado"])

    return movimientos
