"""
Motor de valoración de inventario (FIFO / Costo Promedio).

Expone:
  valorar_movimiento(movimiento) — crea los registros ``ValoracionInventario``
    correspondientes a un ``MovimientoInventario`` ya persistido y devuelve el
    costo unitario de salida calculado (o ``None`` para movimientos que solo
    producen entradas).

El motor opera sobre "pilas" de stock identificadas por
(empresa, producto, variante, almacén). Para cada movimiento:

  - Las ENTRADAS crean una capa de costo (``ValoracionInventario`` con
    ``sentido=ENTRADA``, ``cantidad_restante`` = cantidad).
  - Las SALIDAS consumen capas vivas (``cantidad_restante > 0``) de la pila de
    origen y registran el costo de salida. En FIFO se consumen las capas más
    antiguas primero; en PROMEDIO se usa el costo promedio ponderado de las
    capas vivas. En ambos métodos la depleción de ``cantidad_restante`` se hace
    por antigüedad (no afecta el costo promedio, solo la trazabilidad de capas).

Si una pila no tiene capas vivas suficientes (p. ej. la primera salida histórica
o un ajuste de salida sobre stock sin costo registrado), se usa
``producto.costo_promedio`` como costo de respaldo y se registra una advertencia.

Se llama SIEMPRE dentro de la ``@transaction.atomic`` de ``registrar_movimiento``.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from .models import ValoracionInventario

logger = logging.getLogger(__name__)

# Reutilizamos la clasificación de tipos de services.py para evitar divergencias.
from .services import (  # noqa: E402  (import diferido para evitar ciclo en carga de módulo)
    TIPOS_AJUSTE,
    TIPOS_ENTRADA,
    TIPOS_SALIDA,
    TIPOS_TRANSFERENCIA,
)

CERO = Decimal("0")


def _costo_respaldo(producto) -> Decimal:
    """Costo de salida cuando no hay capas vivas: costo promedio del producto."""
    costo = producto.costo_promedio or CERO
    return Decimal(str(costo))


def _crear_capa_entrada(movimiento, almacen, cantidad: Decimal, costo_unitario: Decimal, metodo: str):
    cantidad = abs(Decimal(str(cantidad)))
    costo_unitario = Decimal(str(costo_unitario))
    return ValoracionInventario.objects.create(
        id_empresa=movimiento.id_empresa,
        id_movimiento=movimiento,
        id_producto=movimiento.id_producto,
        id_variante=movimiento.id_variante,
        id_almacen=almacen,
        sentido="ENTRADA",
        metodo=metodo,
        cantidad=cantidad,
        costo_unitario=costo_unitario,
        valor_total=cantidad * costo_unitario,
        cantidad_restante=cantidad,
    )


def _capas_vivas(movimiento, almacen):
    """Capas ENTRADA con stock no consumido en la pila, bloqueadas para actualizar."""
    return (
        ValoracionInventario.objects.select_for_update()
        .filter(
            id_empresa=movimiento.id_empresa,
            id_producto=movimiento.id_producto,
            id_variante=movimiento.id_variante,
            id_almacen=almacen,
            sentido="ENTRADA",
            cantidad_restante__gt=0,
        )
        .order_by("fecha_creacion", "id_valoracion")  # FIFO: más antigua primero
    )


def _costo_promedio_pila(capas) -> Decimal:
    """Costo promedio ponderado de las capas vivas (valor / cantidad restante)."""
    total_qty = CERO
    total_val = CERO
    for capa in capas:
        total_qty += capa.cantidad_restante
        total_val += capa.cantidad_restante * capa.costo_unitario
    if total_qty <= CERO:
        return CERO
    return total_val / total_qty


def _q4(valor: Decimal) -> Decimal:
    """Cuantiza a 4 decimales (la precisión de los campos de dinero del modelo)."""
    return Decimal(str(valor)).quantize(Decimal("0.0001"))


def _consumir_salida(movimiento, almacen, cantidad: Decimal, metodo: str) -> ValoracionInventario:
    """
    Registra la SALIDA de ``cantidad`` desde la pila de ``almacen`` y devuelve el
    registro ``ValoracionInventario`` creado.

    ``valor_total`` es la fuente de verdad del monto (la base del asiento contable):
      - FIFO: suma del valor de cada capa consumida (más antigua primero).
      - PROMEDIO: ``cantidad`` × promedio ponderado de las capas vivas.
    Lo que no alcanzan las capas vivas se costea al ``costo_promedio`` del producto.
    ``costo_unitario`` se deriva = ``valor_total`` / ``cantidad`` (cuantizado a 4dp).
    """
    cantidad = abs(Decimal(str(cantidad)))
    capas = list(_capas_vivas(movimiento, almacen))
    promedio = _costo_promedio_pila(capas)
    respaldo = _costo_respaldo(movimiento.id_producto)

    pendiente = cantidad
    valor_total = CERO
    for capa in capas:
        if pendiente <= CERO:
            break
        toma = min(capa.cantidad_restante, pendiente)
        capa.cantidad_restante -= toma
        capa.save(update_fields=["cantidad_restante", "fecha_actualizacion"])
        unitario = capa.costo_unitario if metodo == "FIFO" else promedio
        valor_total += toma * unitario
        pendiente -= toma

    # Faltó stock costeado (capas insuficientes): respaldo con costo del producto.
    # En PROMEDIO con capas vivas, el promedio extiende al faltante; sin capas
    # (promedio == 0) o en FIFO, se usa el costo_promedio del producto.
    if pendiente > CERO:
        unitario_faltante = promedio if (metodo == "PROMEDIO" and promedio > CERO) else respaldo
        logger.warning(
            "Valoración SALIDA sin capas suficientes | empresa=%s producto=%s almacen=%s "
            "faltante=%s costo=%s",
            getattr(movimiento.id_empresa, "pk", None),
            getattr(movimiento.id_producto, "pk", None),
            getattr(almacen, "pk", None),
            pendiente,
            unitario_faltante,
        )
        valor_total += pendiente * unitario_faltante

    valor_total = _q4(valor_total)
    costo_unitario = _q4(valor_total / cantidad) if cantidad > CERO else CERO
    return ValoracionInventario.objects.create(
        id_empresa=movimiento.id_empresa,
        id_movimiento=movimiento,
        id_producto=movimiento.id_producto,
        id_variante=movimiento.id_variante,
        id_almacen=almacen,
        sentido="SALIDA",
        metodo=metodo,
        cantidad=cantidad,
        costo_unitario=costo_unitario,
        valor_total=valor_total,
        cantidad_restante=CERO,
    )


def valorar_movimiento(movimiento) -> ValoracionInventario | None:
    """
    Crea los ``ValoracionInventario`` de ``movimiento`` y devuelve el registro de
    SALIDA (con ``costo_unitario`` y ``valor_total``), o ``None`` si el movimiento
    solo produce entradas.

    Reglas por tipo:
      ENTRADA / RECEPCION_COMPRA → capa ENTRADA en almacén destino al costo del
        movimiento (o ``costo_promedio`` del producto si no se indicó).
      SALIDA / DESPACHO_VENTA / …→ consume capas del almacén origen; devuelve la
        valoración de salida.
      TRANSFERENCIA → consume del origen y crea capa en destino al mismo costo.
      AJUSTE → cantidad > 0: entrada; cantidad < 0: salida.
    """
    tipo = movimiento.tipo_movimiento
    producto = movimiento.id_producto
    metodo = getattr(producto, "metodo_valoracion", "PROMEDIO") or "PROMEDIO"
    cantidad = movimiento.cantidad

    if tipo in TIPOS_ENTRADA:
        costo = movimiento.costo_unitario_movimiento
        costo = Decimal(str(costo)) if costo is not None else _costo_respaldo(producto)
        _crear_capa_entrada(movimiento, movimiento.id_almacen_destino, cantidad, costo, metodo)
        return None

    if tipo in TIPOS_SALIDA:
        return _consumir_salida(movimiento, movimiento.id_almacen_origen, cantidad, metodo)

    if tipo in TIPOS_TRANSFERENCIA:
        salida = _consumir_salida(movimiento, movimiento.id_almacen_origen, cantidad, metodo)
        _crear_capa_entrada(
            movimiento, movimiento.id_almacen_destino, cantidad, salida.costo_unitario, metodo
        )
        return salida

    if tipo in TIPOS_AJUSTE:
        if cantidad >= CERO:
            costo = movimiento.costo_unitario_movimiento
            costo = Decimal(str(costo)) if costo is not None else _costo_respaldo(producto)
            _crear_capa_entrada(movimiento, movimiento.id_almacen_destino, cantidad, costo, metodo)
            return None
        return _consumir_salida(movimiento, movimiento.id_almacen_destino, cantidad, metodo)

    # Tipos informativos (RESERVA_VENTA): no generan valoración.
    return None
