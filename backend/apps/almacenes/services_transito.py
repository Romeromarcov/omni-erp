"""Servicios de transferencia inter-almacén en tránsito en 2 pasos (Plan 09 Fase 5.4).

Desacopla salida del almacén origen (estado ``EN_TRANSITO``) de la recepción física en
destino (estado ``RECIBIDA``), preservando trazabilidad y ámbito contable.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.inventario.models import Producto
from apps.inventario.services import MovimientoInvalidoError, StockInsuficienteError, registrar_movimiento

from .models import Almacen, DetalleTransferenciaTransito, TransferenciaTransito, UbicacionAlmacen

_CERO = Decimal("0")
_Q4 = Decimal("0.0001")


class TransferenciaTransitoError(Exception):
    """Error de dominio en transferencias inter-almacén en tránsito."""


def _q4(val: Decimal) -> Decimal:
    return val.quantize(_Q4, rounding=ROUND_HALF_UP)


def _dec(val: Any, default: Decimal | None = None) -> Decimal:
    if val is None or val == "":
        if default is not None:
            return default
        raise TransferenciaTransitoError("Valor numérico requerido.")
    if isinstance(val, Decimal):
        return val
    try:
        dec = Decimal(str(val).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TransferenciaTransitoError(f"Valor numérico inválido: {val!r}.") from exc
    if not dec.is_finite():
        raise TransferenciaTransitoError(f"Valor numérico no finito: {val!r}.")
    return dec


def _numero_transito(empresa) -> str:
    n = TransferenciaTransito.objects.filter(id_empresa=empresa).count() + 1
    return f"TRF-{n:06d}"


@transaction.atomic
def despachar_transferencia_transito(
    *,
    empresa,
    almacen_origen: Almacen,
    almacen_destino: Almacen,
    usuario,
    items: list[dict[str, Any]],
    ubicacion_transito: UbicacionAlmacen | None = None,
    ambito: str = "FISCAL",
    numero: str | None = None,
    observaciones: str = "",
) -> TransferenciaTransito:
    """Paso 1: egresa el stock del almacén origen y crea la TransferenciaTransito EN_TRANSITO."""
    if almacen_origen.id_empresa_id != empresa.pk or almacen_destino.id_empresa_id != empresa.pk:
        raise TransferenciaTransitoError("Los almacenes deben pertenecer a la empresa indicada.")
    if almacen_origen.pk == almacen_destino.pk:
        raise TransferenciaTransitoError("El almacén de origen y destino deben ser distintos.")
    if ambito not in ("FISCAL", "GERENCIAL"):
        raise TransferenciaTransitoError(f"Ámbito contable inválido: {ambito!r}.")
    if not items:
        raise TransferenciaTransitoError("Debe especificar al menos una línea de producto para despachar.")
    if ubicacion_transito is not None and ubicacion_transito.id_empresa_id != empresa.pk:
        raise TransferenciaTransitoError("La ubicación de tránsito no pertenece a la empresa.")

    ahora = timezone.now()
    num = (numero or "").strip() or _numero_transito(empresa)
    trans = TransferenciaTransito.objects.create(
        id_empresa=empresa,
        numero=num,
        id_almacen_origen=almacen_origen,
        id_almacen_destino=almacen_destino,
        id_ubicacion_transito=ubicacion_transito,
        ambito=ambito,
        estado="EN_TRANSITO",
        fecha_despacho=ahora,
        id_usuario_despacho=usuario,
        observaciones=observaciones or "",
    )

    for it in items:
        producto: Producto = it["producto"]
        variante = it.get("variante")
        qty = _q4(_dec(it["cantidad"]))
        if qty <= _CERO:
            raise TransferenciaTransitoError("La cantidad despachada debe ser mayor a cero.")
        if producto.id_empresa_id != empresa.pk:
            raise TransferenciaTransitoError(f"El producto '{producto}' no pertenece a la empresa.")

        try:
            mov = registrar_movimiento(
                empresa=empresa,
                fecha_hora_movimiento=ahora,
                tipo_movimiento="SALIDA",
                producto=producto,
                variante=variante,
                cantidad=qty,
                almacen_origen=almacen_origen,
                documento_origen_id=trans.id_transferencia_transito,
                nombre_modelo_origen="TransferenciaTransito",
                usuario=usuario,
                observaciones=f"Despacho tránsito inter-almacén {num}",
                ambito=ambito,
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise TransferenciaTransitoError(str(exc)) from exc

        costo_u = _q4(_dec(mov.costo_unitario_movimiento, producto.costo_promedio or _CERO))
        DetalleTransferenciaTransito.objects.create(
            id_empresa=empresa,
            id_transferencia=trans,
            id_producto=producto,
            id_variante=variante,
            cantidad_despachada=qty,
            costo_unitario=costo_u,
        )

    return trans


@transaction.atomic
def recibir_transferencia_transito(
    *,
    transferencia: TransferenciaTransito,
    usuario,
    cantidades_recibidas: dict[str, Any] | None = None,
    observaciones: str = "",
) -> dict[str, Any]:
    """Paso 2: ingresa mercancía en destino al costo unitario de salida y cierra la transferencia."""
    trans_locked = (
        TransferenciaTransito.objects.select_for_update(of=("self",))
        .select_related("id_empresa", "id_almacen_destino")
        .get(pk=transferencia.pk)
    )
    if trans_locked.estado != "EN_TRANSITO":
        raise TransferenciaTransitoError(
            f"Solo se pueden recibir transferencias EN_TRANSITO. Estado actual: {trans_locked.estado}."
        )

    detalles = list(trans_locked.detalles.select_for_update(of=("self",)).select_related("id_producto", "id_variante"))
    if not detalles:
        raise TransferenciaTransitoError("La transferencia no contiene líneas de detalle.")

    ahora = timezone.now()
    movimientos = []
    mermas: list[dict[str, Any]] = []

    for det in detalles:
        qty_rec = _q4(
            _dec(cantidades_recibidas[str(det.id_detalle)])
            if cantidades_recibidas and str(det.id_detalle) in cantidades_recibidas
            else det.cantidad_despachada
        )
        if qty_rec < _CERO or qty_rec > det.cantidad_despachada:
            raise TransferenciaTransitoError(
                f"Cantidad recibida inválida ({qty_rec}) para '{det.id_producto.nombre_producto}'; "
                f"debe estar entre 0 y {det.cantidad_despachada}."
            )

        det.cantidad_recibida = qty_rec
        det.save(update_fields=["cantidad_recibida", "fecha_actualizacion"])

        if qty_rec > _CERO:
            try:
                mov = registrar_movimiento(
                    empresa=trans_locked.id_empresa,
                    fecha_hora_movimiento=ahora,
                    tipo_movimiento="ENTRADA",
                    producto=det.id_producto,
                    variante=det.id_variante,
                    cantidad=qty_rec,
                    almacen_destino=trans_locked.id_almacen_destino,
                    costo_unitario=det.costo_unitario,
                    documento_origen_id=trans_locked.id_transferencia_transito,
                    nombre_modelo_origen="TransferenciaTransito",
                    usuario=usuario,
                    observaciones=f"Recepción tránsito inter-almacén {trans_locked.numero}",
                    ambito=trans_locked.ambito,
                )
            except (StockInsuficienteError, MovimientoInvalidoError) as exc:
                raise TransferenciaTransitoError(str(exc)) from exc
            movimientos.append(mov)

        if qty_rec < det.cantidad_despachada:
            mermas.append(
                {
                    "id_detalle": str(det.id_detalle),
                    "id_producto": str(det.id_producto_id),
                    "cantidad_despachada": str(det.cantidad_despachada),
                    "cantidad_recibida": str(qty_rec),
                    "diferencia_merma": str(_q4(det.cantidad_despachada - qty_rec)),
                }
            )

    trans_locked.estado = "RECIBIDA"
    trans_locked.fecha_recepcion = ahora
    trans_locked.id_usuario_recepcion = usuario
    if observaciones:
        trans_locked.observaciones = (
            f"{trans_locked.observaciones}\n{observaciones}".strip() if trans_locked.observaciones else observaciones
        )
    trans_locked.save(
        update_fields=["estado", "fecha_recepcion", "id_usuario_recepcion", "observaciones", "fecha_actualizacion"]
    )

    return {
        "transferencia": trans_locked,
        "movimientos_entrada": [str(m.pk) for m in movimientos],
        "mermas": mermas,
    }


@transaction.atomic
def cancelar_transferencia_transito(transferencia: TransferenciaTransito, usuario) -> TransferenciaTransito:
    """Cancela una transferencia EN_TRANSITO devolviendo el stock al almacén origen."""
    trans_locked = (
        TransferenciaTransito.objects.select_for_update(of=("self",))
        .select_related("id_empresa", "id_almacen_origen")
        .get(pk=transferencia.pk)
    )
    if trans_locked.estado != "EN_TRANSITO":
        raise TransferenciaTransitoError(
            f"Solo se pueden cancelar transferencias EN_TRANSITO. Estado actual: {trans_locked.estado}."
        )

    ahora = timezone.now()
    for det in trans_locked.detalles.select_related("id_producto", "id_variante"):
        try:
            registrar_movimiento(
                empresa=trans_locked.id_empresa,
                fecha_hora_movimiento=ahora,
                tipo_movimiento="ENTRADA",
                producto=det.id_producto,
                variante=det.id_variante,
                cantidad=det.cantidad_despachada,
                almacen_destino=trans_locked.id_almacen_origen,
                costo_unitario=det.costo_unitario,
                documento_origen_id=trans_locked.id_transferencia_transito,
                nombre_modelo_origen="TransferenciaTransito",
                usuario=usuario,
                observaciones=f"Reverso cancelación tránsito {trans_locked.numero}",
                ambito=trans_locked.ambito,
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise TransferenciaTransitoError(str(exc)) from exc

    trans_locked.estado = "CANCELADA"
    trans_locked.save(update_fields=["estado", "fecha_actualizacion"])
    return trans_locked
