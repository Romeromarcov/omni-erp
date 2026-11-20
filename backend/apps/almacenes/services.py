"""Servicios transaccionales de stock por ubicación de almacén (Plan 08 §B.3).

Expone:
  - ``transferir_entre_ubicaciones(...)``
  - ``reservar_ubicacion(...)``
  - ``UbicacionOperacionError`` / ``AutorizacionUbicacionError``
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.inventario.models import MovimientoInventario
from apps.inventario.services import registrar_movimiento

from .models import Almacen, StockUbicacion, UbicacionAlmacen

_CERO = Decimal("0")
_Q4 = Decimal("0.0001")


class UbicacionOperacionError(Exception):
    """Error de dominio en operaciones de stock por ubicación."""


class AutorizacionUbicacionError(UbicacionOperacionError):
    """La ubicación involucrada requiere autorización de supervisor."""


def _parse_decimal_positivo(valor: Any, campo: str = "cantidad") -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise UbicacionOperacionError(f"El campo '{campo}' debe ser numérico.")
    try:
        dec = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise UbicacionOperacionError(f"Valor numérico inválido para '{campo}': {valor!r}.") from exc
    if not dec.is_finite() or dec <= _CERO:
        raise UbicacionOperacionError(f"El campo '{campo}' debe ser mayor a cero.")
    return dec.quantize(_Q4)


def _validar_contexto_ubicacion(
    *,
    empresa,
    almacen: Almacen,
    ubicacion: UbicacionAlmacen,
    producto,
    variante=None,
    etiqueta: str = "ubicación",
) -> None:
    if empresa is None or almacen is None or ubicacion is None or producto is None:
        raise UbicacionOperacionError("Empresa, almacén, ubicación y producto son obligatorios.")
    if str(almacen.id_empresa_id) != str(empresa.pk):
        raise UbicacionOperacionError("El almacén no pertenece a la empresa indicada.")
    if not almacen.usa_ubicaciones:
        raise UbicacionOperacionError(
            f"El almacén '{almacen.nombre_almacen}' no tiene habilitado el manejo por ubicaciones."
        )
    if str(ubicacion.id_empresa_id) != str(empresa.pk) or str(ubicacion.id_almacen_id) != str(almacen.pk):
        raise UbicacionOperacionError(f"La {etiqueta} no pertenece al almacén y empresa indicados.")
    if not ubicacion.activo:
        raise UbicacionOperacionError(f"La {etiqueta} '{ubicacion.codigo_ubicacion}' está inactiva.")
    if str(producto.id_empresa_id) != str(empresa.pk):
        raise UbicacionOperacionError("El producto no pertenece a la empresa indicada.")
    if variante is not None and str(variante.id_producto_id) != str(producto.pk):
        raise UbicacionOperacionError("La variante no pertenece al producto indicado.")


@transaction.atomic
def transferir_entre_ubicaciones(
    *,
    empresa,
    almacen: Almacen,
    ubicacion_origen: UbicacionAlmacen,
    ubicacion_destino: UbicacionAlmacen,
    producto,
    variante=None,
    cantidad,
    usuario,
    autorizado_por=None,
    observaciones: str = "",
) -> tuple[StockUbicacion, StockUbicacion, MovimientoInventario]:
    """Transfiere stock entre dos ubicaciones de un mismo almacén con ``usa_ubicaciones=True``."""
    if usuario is None:
        raise UbicacionOperacionError("El usuario solicitante es obligatorio.")

    _validar_contexto_ubicacion(
        empresa=empresa,
        almacen=almacen,
        ubicacion=ubicacion_origen,
        producto=producto,
        variante=variante,
        etiqueta="ubicación origen",
    )
    _validar_contexto_ubicacion(
        empresa=empresa,
        almacen=almacen,
        ubicacion=ubicacion_destino,
        producto=producto,
        variante=variante,
        etiqueta="ubicación destino",
    )
    if ubicacion_origen.pk == ubicacion_destino.pk:
        raise UbicacionOperacionError("La ubicación origen y la ubicación destino deben ser distintas.")

    cantidad_dec = _parse_decimal_positivo(cantidad, "cantidad")

    if ubicacion_origen.requiere_autorizacion or ubicacion_destino.requiere_autorizacion:
        if autorizado_por is not None:
            autorizado_valido = (
                autorizado_por.empresas.filter(pk=empresa.pk).exists()
                or getattr(autorizado_por, "is_staff", False)
                or getattr(autorizado_por, "is_superuser", False)
            )
            if not autorizado_valido:
                raise AutorizacionUbicacionError(
                    "El usuario autorizador no pertenece a la empresa ni tiene permisos de supervisor."
                )
        elif not (getattr(usuario, "is_staff", False) or getattr(usuario, "is_superuser", False)):
            raise AutorizacionUbicacionError(
                "Una de las ubicaciones requiere autorización de supervisor (autorizado_por o usuario staff)."
            )

    orig_obj = StockUbicacion.objects.filter(
        id_empresa=empresa,
        id_almacen=almacen,
        id_ubicacion=ubicacion_origen,
        id_producto=producto,
        id_variante=variante,
    ).first()
    if orig_obj is None:
        raise UbicacionOperacionError(
            f"Sin existencias en ubicación origen '{ubicacion_origen.codigo_ubicacion}' para '{producto}'."
        )

    dest_obj, _ = StockUbicacion.objects.get_or_create(
        id_empresa=empresa,
        id_almacen=almacen,
        id_ubicacion=ubicacion_destino,
        id_producto=producto,
        id_variante=variante,
        defaults={"cantidad_disponible": _CERO, "cantidad_reservada": _CERO},
    )

    # Lock determinístico por PK para evitar deadlocks en transferencias cruzadas.
    pks = sorted([orig_obj.pk, dest_obj.pk], key=str)
    locked = {obj.pk: obj for obj in StockUbicacion.objects.select_for_update().filter(pk__in=pks).order_by("pk")}
    orig = locked[orig_obj.pk]
    dest = locked[dest_obj.pk]

    libre = orig.cantidad_disponible - orig.cantidad_reservada
    if libre < cantidad_dec:
        raise UbicacionOperacionError(
            f"Stock libre insuficiente en ubicación '{ubicacion_origen.codigo_ubicacion}'. "
            f"Libre: {libre}, solicitado: {cantidad_dec}."
        )

    orig.cantidad_disponible -= cantidad_dec
    orig.save(update_fields=["cantidad_disponible", "fecha_actualizacion"])

    dest.cantidad_disponible += cantidad_dec
    dest_fields = ["cantidad_disponible", "fecha_actualizacion"]
    if not dest.activo:
        dest.activo = True
        dest_fields.append("activo")
    dest.save(update_fields=dest_fields)

    obs_limpia = (observaciones or "").strip()
    traza = f"Ubicación {ubicacion_origen.codigo_ubicacion} -> {ubicacion_destino.codigo_ubicacion}"
    obs_final = f"{traza} | {obs_limpia}" if obs_limpia else traza
    movimiento = registrar_movimiento(
        empresa=empresa,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="TRANSFERENCIA_UBICACION",
        producto=producto,
        variante=variante,
        cantidad=cantidad_dec,
        almacen_origen=almacen,
        almacen_destino=almacen,
        documento_origen_id=ubicacion_destino.id_ubicacion,
        nombre_modelo_origen="UbicacionAlmacen",
        usuario=usuario,
        observaciones=obs_final,
    )
    return orig, dest, movimiento


@transaction.atomic
def reservar_ubicacion(
    *,
    empresa,
    almacen: Almacen,
    ubicacion: UbicacionAlmacen,
    producto,
    variante=None,
    cantidad,
    liberar: bool = False,
) -> StockUbicacion:
    """Reserva o libera stock en una ``UbicacionAlmacen`` de forma atómica."""
    _validar_contexto_ubicacion(
        empresa=empresa,
        almacen=almacen,
        ubicacion=ubicacion,
        producto=producto,
        variante=variante,
        etiqueta="ubicación",
    )
    cantidad_dec = _parse_decimal_positivo(cantidad, "cantidad")

    try:
        stock = StockUbicacion.objects.select_for_update().get(
            id_empresa=empresa,
            id_almacen=almacen,
            id_ubicacion=ubicacion,
            id_producto=producto,
            id_variante=variante,
        )
    except StockUbicacion.DoesNotExist as exc:
        raise UbicacionOperacionError(
            f"No existe stock en la ubicación '{ubicacion.codigo_ubicacion}' para '{producto}'."
        ) from exc

    if liberar:
        if stock.cantidad_reservada < cantidad_dec:
            raise UbicacionOperacionError(
                f"Reserva insuficiente para liberar. Reservado: {stock.cantidad_reservada}, solicitado: {cantidad_dec}."
            )
        stock.cantidad_reservada -= cantidad_dec
    else:
        libre = stock.cantidad_disponible - stock.cantidad_reservada
        if libre < cantidad_dec:
            raise UbicacionOperacionError(
                f"Stock libre insuficiente en ubicación '{ubicacion.codigo_ubicacion}'. "
                f"Libre: {libre}, solicitado: {cantidad_dec}."
            )
        stock.cantidad_reservada += cantidad_dec

    stock.save(update_fields=["cantidad_reservada", "fecha_actualizacion"])
    return stock
