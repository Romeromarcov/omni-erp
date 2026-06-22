"""
Lógica de negocio del ciclo de compras (R-CODE-11 en recepción y factura).

Flujo:
  aprobar_orden_compra()      → OC pasa a APROBADA
  registrar_recepcion()       → RecepcionMercancia + MovimientoInventario(RECEPCION_COMPRA)
                                + CuentaPorPagar + AsientoContable(RECEPCION_MERCANCIA)
  registrar_factura_compra()  → FacturaCompra + AsientoContable(FACTURA_COMPRA)
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.contabilidad.services import AsientoError, generar_asiento_o_fallar
from apps.inventario.services import MovimientoInvalidoError, StockInsuficienteError, registrar_movimiento


# ── Excepción de dominio ──────────────────────────────────────────────────────


class CompraError(Exception):
    pass


# ── aprobar_orden_compra ──────────────────────────────────────────────────────


@transaction.atomic
def aprobar_orden_compra(orden_compra, usuario) -> None:
    """
    Cambia el estado de la OC de BORRADOR/ENVIADA a APROBADA.
    """
    if orden_compra.estado not in ("BORRADOR", "ENVIADA"):
        raise CompraError(
            f"Solo se aprueban órdenes en BORRADOR o ENVIADA. Estado actual: {orden_compra.estado}"
        )
    orden_compra.estado = "APROBADA"
    orden_compra.save(update_fields=["estado"])


# ── registrar_recepcion ───────────────────────────────────────────────────────


@transaction.atomic
def registrar_recepcion(orden_compra, almacen, usuario, items: list[dict]) -> dict:
    """
    Registra la recepción de mercancía para una OC aprobada.

    Args:
        orden_compra: Instancia OrdenCompra en estado APROBADA.
        almacen:      Instancia Almacen destino de la mercancía.
        usuario:      Instancia Usuarios que registra.
        items:        Lista de dicts con keys: producto, cantidad, costo_unitario.
                      Ejemplo: [{"producto": <Producto>, "cantidad": 10, "costo_unitario": "25.00"}]

    Returns:
        {"recepcion": RecepcionMercancia, "movimientos": [...], "cxp": CuentaPorPagar, "asiento": AsientoContable}
    """
    from apps.compras.models import DetalleRecepcionMercancia, RecepcionMercancia
    from apps.cuentas_por_pagar.models import CuentaPorPagar

    if orden_compra.estado != "APROBADA":
        raise CompraError(
            f"Solo se puede recepcionar contra una OC APROBADA. Estado: {orden_compra.estado}"
        )
    if not items:
        raise CompraError("Debe especificar al menos un ítem para recepcionar.")

    empresa = orden_compra.id_empresa
    fecha_recepcion = timezone.now().date()

    # Enforcement de cierre de período fiscal: la recepción postea un asiento
    # (RECEPCION_MERCANCIA); no se permite contra un período ya cerrado.
    from apps.fiscal.services import PeriodoCerradoError, validar_periodo_abierto

    try:
        validar_periodo_abierto(empresa, fecha_recepcion)
    except PeriodoCerradoError as exc:
        raise CompraError(str(exc)) from exc

    monto_total = sum(
        Decimal(str(it["cantidad"])) * Decimal(str(it["costo_unitario"])) for it in items
    )

    recepcion = RecepcionMercancia.objects.create(
        id_empresa=empresa,
        id_orden_compra=orden_compra,
        fecha_recepcion=fecha_recepcion,
        monto_total=monto_total,
    )

    movimientos = []
    for it in items:
        producto = it["producto"]
        cantidad = Decimal(str(it["cantidad"]))
        costo_u = Decimal(str(it["costo_unitario"]))
        subtotal = cantidad * costo_u

        DetalleRecepcionMercancia.objects.create(
            id_recepcion=recepcion,
            id_producto=producto,
            cantidad_recibida=cantidad,
            costo_unitario=costo_u,
            subtotal=subtotal,
        )

        try:
            mov = registrar_movimiento(
                empresa=empresa,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="RECEPCION_COMPRA",
                producto=producto,
                cantidad=cantidad,
                almacen_destino=almacen,
                costo_unitario=costo_u,
                documento_origen_id=recepcion.id_recepcion,
                nombre_modelo_origen="RecepcionMercancia",
                usuario=usuario,
                observaciones=f"Recepción OC {orden_compra.numero_orden}",
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise CompraError(str(exc)) from exc
        movimientos.append(mov)

    dias_pago = getattr(orden_compra.id_proveedor, "dias_pago", None) or 30
    cxp = CuentaPorPagar.objects.create(
        id_empresa=empresa,
        id_proveedor=orden_compra.id_proveedor,
        id_factura_compra_id=None,  # se enlazará cuando llegue la factura
        id_recepcion=recepcion,  # ancla para re-vincular la factura después
        monto_total=monto_total,
        monto_pendiente=monto_total,
        fecha_emision=timezone.now().date(),
        fecha_vencimiento=timezone.now().date() + timezone.timedelta(days=dias_pago),
        estado="PENDIENTE",
        observaciones=f"Recepción OC {orden_compra.numero_orden}",
    )

    # H-BUG-1: R-CODE-11 centralizado. Si la empresa tiene contabilidad activa y
    # falta el mapeo, esto lanza AsientoError (la transacción revierte); si no,
    # continúa sin asiento. Cualquier AsientoError real también propaga.
    asiento = None
    try:
        asiento, _ = generar_asiento_o_fallar("RECEPCION_MERCANCIA", recepcion, empresa, usuario=usuario)
    except AsientoError as exc:
        raise CompraError(f"Error generando asiento de recepción: {exc}") from exc

    return {"recepcion": recepcion, "movimientos": movimientos, "cxp": cxp, "asiento": asiento}


# ── registrar_factura_compra ──────────────────────────────────────────────────


@transaction.atomic
def registrar_factura_compra(recepcion, numero_factura: str, fecha_emision=None, usuario=None) -> dict:
    """
    Registra la factura del proveedor asociada a una recepción y genera el asiento (R-CODE-11).

    Returns:
        {"factura": FacturaCompra, "asiento": AsientoContable | None,
         "cxp": CuentaPorPagar | None}  # la CxP de la recepción, ya re-vinculada
    """
    from apps.compras.models import FacturaCompra

    empresa = recepcion.id_empresa
    fecha = fecha_emision or timezone.now().date()

    # Enforcement de cierre de período fiscal: la factura de compra postea un
    # asiento (FACTURA_COMPRA); no se emite contra un período ya cerrado.
    from apps.fiscal.services import PeriodoCerradoError, validar_periodo_abierto

    try:
        validar_periodo_abierto(empresa, fecha)
    except PeriodoCerradoError as exc:
        raise CompraError(str(exc)) from exc

    factura = FacturaCompra.objects.create(
        id_empresa=empresa,
        id_orden_compra=recepcion.id_orden_compra,
        id_recepcion=recepcion,
        numero_factura=numero_factura,
        fecha_emision=fecha,
        monto_total=recepcion.monto_total,
    )

    # Re-vincula la CxP nacida en la recepción a la factura recién registrada.
    # Se localiza por su ancla id_recepcion (multi-tenant: filtrada por empresa)
    # y solo si aún no estaba vinculada, para no pisar un enlace previo.
    from apps.cuentas_por_pagar.models import CuentaPorPagar

    cxp = CuentaPorPagar.objects.filter(
        id_empresa=empresa,
        id_recepcion=recepcion,
        id_factura_compra__isnull=True,
    ).first()
    if cxp is not None:
        cxp.id_factura_compra = factura
        cxp.save(update_fields=["id_factura_compra"])

    # H-BUG-1: R-CODE-11 centralizado (ver registrar_recepcion).
    asiento = None
    try:
        asiento, _ = generar_asiento_o_fallar("FACTURA_COMPRA", factura, empresa, usuario=usuario)
    except AsientoError as exc:
        raise CompraError(f"Error generando asiento de factura compra: {exc}") from exc

    return {"factura": factura, "asiento": asiento, "cxp": cxp}
