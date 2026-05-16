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
TIPOS_SALIDA = frozenset({"SALIDA", "DESPACHO_VENTA", "CONSUMO_PRODUCCION"})
TIPOS_TRANSFERENCIA = frozenset({"TRANSFERENCIA"})
TIPOS_AJUSTE = frozenset({"AJUSTE"})

ALL_TIPOS = TIPOS_ENTRADA | TIPOS_SALIDA | TIPOS_TRANSFERENCIA | TIPOS_AJUSTE


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

    return movimiento
