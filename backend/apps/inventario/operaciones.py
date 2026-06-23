"""
Operaciones de inventario con stepper configurable (recepción / entrega).

Flujo:
  crear_operacion()   → crea la OperacionInventario en EN_PROCESO y toma un
                        snapshot de los PasoOperacion activos del almacén.
  confirmar_paso()    → confirma un paso; exige que los pasos anteriores estén
                        confirmados (PasoFueraDeOrdenError → HTTP 400). Al
                        confirmar el último paso, completa la operación: mueve el
                        stock (registrar_movimiento, que valúa y costea) y genera
                        los asientos contables según el tipo de operación/origen.

Derivación del movimiento físico al completar:
  RECEPCION + PURCHASE     → RECEPCION_COMPRA  (+ asiento RECEPCION_MERCANCIA: DR Inventario / CR CxP)
  ENTREGA   + SALE         → DESPACHO_VENTA    (COGS automático + asiento NOTA_VENTA: DR CxC / CR Ingresos)
  ENTREGA   + TRANSFER     → TRANSFERENCIA     (solo mueve stock entre almacenes)
  ENTREGA   + RETURN/SCRAP → SALIDA            (solo mueve stock)
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    OperacionInventario,
    OperacionInventarioLinea,
    OperacionInventarioPaso,
    PasoOperacion,
)
from .services import registrar_movimiento

logger = logging.getLogger(__name__)

CERO = Decimal("0")


class OperacionError(Exception):
    """Datos inválidos al crear u operar una OperacionInventario."""


class PasoFueraDeOrdenError(Exception):
    """Se intentó confirmar un paso antes de confirmar uno anterior."""


def _numero(empresa, tipo_operacion: str) -> str:
    prefijo = "REC" if tipo_operacion == "RECEPCION" else "ENT"
    n = OperacionInventario.objects.filter(id_empresa=empresa, tipo_operacion=tipo_operacion).count() + 1
    return f"{prefijo}-{n:06d}"


@transaction.atomic
def crear_operacion(
    *,
    empresa,
    almacen,
    tipo_operacion: str,
    origen_tipo: str,
    lineas,
    usuario,
    fecha=None,
    origen_id=None,
    almacen_contraparte=None,
    motivo: str = "",
) -> OperacionInventario:
    """
    Crea una OperacionInventario EN_PROCESO con el snapshot de pasos del almacén.

    `lineas`: iterable de dicts {producto, variante?, cantidad, costo_unitario?}.
    """
    if tipo_operacion not in dict(OperacionInventario.TIPOS_OPERACION):
        raise OperacionError(f"tipo_operacion inválido: {tipo_operacion!r}")
    if origen_tipo not in dict(OperacionInventario.ORIGENES):
        raise OperacionError(f"origen_tipo inválido: {origen_tipo!r}")

    lineas = list(lineas)
    if not lineas:
        raise OperacionError("La operación requiere al menos una línea.")

    if origen_tipo in ("RETURN", "SCRAP") and not motivo:
        raise OperacionError("El motivo es obligatorio para devoluciones y desechos.")

    if origen_tipo == "TRANSFER":
        if almacen_contraparte is None:
            raise OperacionError("La transferencia requiere almacén contraparte (destino).")
        if almacen_contraparte == almacen:
            raise OperacionError("El almacén de origen y destino deben ser distintos.")

    if tipo_operacion == "ENTREGA" and origen_tipo == "SALE" and not origen_id:
        raise OperacionError("La entrega de venta requiere origen_id (NotaVenta/FacturaFiscal).")

    pasos_config = list(
        PasoOperacion.objects.filter(
            id_empresa=empresa, id_almacen=almacen, tipo_operacion=tipo_operacion, activo=True
        ).order_by("secuencia")
    )
    if not pasos_config:
        raise OperacionError(
            f"El almacén no tiene pasos configurados para {tipo_operacion}. "
            "Configure PasoOperacion antes de crear la operación."
        )

    # Numeración resiliente a carreras: si dos creaciones concurrentes calculan el
    # mismo numero, la unique_together(id_empresa, numero) hace fallar a una; se
    # reintenta dentro de un savepoint sin romper la transacción externa.
    operacion = None
    for intento in range(5):
        try:
            with transaction.atomic():
                operacion = OperacionInventario.objects.create(
                    id_empresa=empresa,
                    numero=_numero(empresa, tipo_operacion),
                    tipo_operacion=tipo_operacion,
                    origen_tipo=origen_tipo,
                    origen_id=origen_id,
                    id_almacen=almacen,
                    id_almacen_contraparte=almacen_contraparte,
                    estado="EN_PROCESO",
                    motivo=motivo,
                    fecha=fecha or timezone.now(),
                )
            break
        except IntegrityError:
            if intento == 4:
                raise
            continue

    for paso in pasos_config:
        OperacionInventarioPaso.objects.create(
            id_operacion=operacion, secuencia=paso.secuencia, nombre_paso=paso.nombre_paso
        )

    for ln in lineas:
        cantidad = Decimal(str(ln["cantidad"]))
        if cantidad <= 0:
            raise OperacionError("La cantidad de cada línea debe ser mayor a cero.")
        costo = ln.get("costo_unitario")
        OperacionInventarioLinea.objects.create(
            id_operacion=operacion,
            id_producto=ln["producto"],
            id_variante=ln.get("variante"),
            cantidad=cantidad,
            costo_unitario=Decimal(str(costo)) if costo is not None else None,
        )

    return operacion


@transaction.atomic
def confirmar_paso(*, operacion: OperacionInventario, paso: OperacionInventarioPaso, usuario) -> OperacionInventario:
    """
    Confirma `paso`. Exige que todos los pasos anteriores estén confirmados.
    Al confirmar el último paso, completa la operación (mueve stock + asientos).

    Toma un lock pesimista sobre la operación (select_for_update) para serializar
    confirmaciones concurrentes: sin él, dos confirmaciones simultáneas de los dos
    últimos pasos podrían ambas observar "todos confirmados" y completar dos veces.
    """
    # Re-lee bajo lock (TOCTOU): la operación y el paso pueden haber cambiado.
    operacion = OperacionInventario.objects.select_for_update().get(pk=operacion.pk)
    paso = OperacionInventarioPaso.objects.select_for_update().get(pk=paso.pk)

    if operacion.estado != "EN_PROCESO":
        raise OperacionError(f"La operación no está en proceso (estado: {operacion.estado}).")
    if paso.id_operacion_id != operacion.id_operacion:
        raise OperacionError("El paso no pertenece a esta operación.")
    if paso.confirmado:
        raise OperacionError("El paso ya fue confirmado.")

    anteriores_sin_confirmar = operacion.pasos.filter(
        secuencia__lt=paso.secuencia, confirmado=False
    ).exists()
    if anteriores_sin_confirmar:
        raise PasoFueraDeOrdenError(
            f"No se puede confirmar el paso {paso.secuencia} ('{paso.nombre_paso}') "
            "antes de confirmar los pasos anteriores."
        )

    paso.confirmado = True
    paso.id_usuario_confirmacion = usuario
    paso.fecha_confirmacion = timezone.now()
    paso.save(update_fields=["confirmado", "id_usuario_confirmacion", "fecha_confirmacion"])

    if not operacion.pasos.filter(confirmado=False).exists():
        _completar_operacion(operacion, usuario)

    return operacion


def _completar_operacion(operacion: OperacionInventario, usuario) -> None:
    """Mueve el stock de todas las líneas y genera los asientos correspondientes."""
    from apps.contabilidad.services import generar_asiento_o_fallar

    empresa = operacion.id_empresa

    # ── Venta: delegar al chokepoint canónico de ventas ──────────────────────
    # confirmar_nota_venta es el ÚNICO dueño del ciclo de venta: transiciona la
    # NotaVenta a ENTREGADA (idempotente: exige BORRADOR, así no se despacha dos
    # veces ni por el stepper ni por el flujo de ventas), descuenta stock con su
    # COGS (DESPACHO_VENTA), crea la CxC y posa el asiento de ingresos. Evita el
    # doble registro de inventario y de asientos (B1/B2).
    if operacion.origen_tipo == "SALE":
        _completar_venta(operacion, usuario)
        operacion.estado = "COMPLETADA"
        operacion.save(update_fields=["estado"])
        return

    lineas = list(operacion.lineas.select_related("id_producto", "id_variante"))
    valor_recepcion = CERO

    for ln in lineas:
        if operacion.tipo_operacion == "RECEPCION":
            mov = registrar_movimiento(
                empresa=empresa,
                fecha_hora_movimiento=operacion.fecha,
                tipo_movimiento="RECEPCION_COMPRA",
                producto=ln.id_producto,
                variante=ln.id_variante,
                cantidad=ln.cantidad,
                almacen_destino=operacion.id_almacen,
                costo_unitario=ln.costo_unitario,
                documento_origen_id=operacion.id_operacion,
                nombre_modelo_origen="OperacionInventario",
                usuario=usuario,
                observaciones=f"Recepción {operacion.numero}",
            )
            # Fuente de verdad del monto = la capa de valoración creada (no un
            # re-cálculo de costo_promedio, que podría divergir del stock real).
            capa = mov.valoraciones.filter(sentido="ENTRADA").first()
            if capa is not None:
                valor_recepcion += capa.valor_total

        elif operacion.origen_tipo == "TRANSFER":
            registrar_movimiento(
                empresa=empresa,
                fecha_hora_movimiento=operacion.fecha,
                tipo_movimiento="TRANSFERENCIA",
                producto=ln.id_producto,
                variante=ln.id_variante,
                cantidad=ln.cantidad,
                almacen_origen=operacion.id_almacen,
                almacen_destino=operacion.id_almacen_contraparte,
                documento_origen_id=operacion.id_operacion,
                nombre_modelo_origen="OperacionInventario",
                usuario=usuario,
                observaciones=f"Transferencia {operacion.numero}",
            )

        else:  # RETURN / SCRAP → salida simple
            registrar_movimiento(
                empresa=empresa,
                fecha_hora_movimiento=operacion.fecha,
                tipo_movimiento="SALIDA",
                producto=ln.id_producto,
                variante=ln.id_variante,
                cantidad=ln.cantidad,
                almacen_origen=operacion.id_almacen,
                documento_origen_id=operacion.id_operacion,
                nombre_modelo_origen="OperacionInventario",
                usuario=usuario,
                observaciones=f"{operacion.get_origen_tipo_display()} {operacion.numero}: {operacion.motivo}",
            )

    # DR Inventario / CR Cuentas por Pagar (al valor realmente layereado).
    if operacion.tipo_operacion == "RECEPCION" and valor_recepcion > 0:
        generar_asiento_o_fallar(
            "RECEPCION_MERCANCIA", operacion, empresa, monto=valor_recepcion, usuario=usuario
        )

    operacion.estado = "COMPLETADA"
    operacion.save(update_fields=["estado"])


def _completar_venta(operacion, usuario) -> None:
    """
    Despacha la NotaVenta vinculada a través del chokepoint canónico de ventas
    (confirmar_nota_venta): stock + COGS + CxC + asiento de ingresos, una sola vez.
    """
    from apps.ventas.models import NotaVenta
    from apps.ventas.services import confirmar_nota_venta

    nota = NotaVenta.objects.filter(
        id_nota_venta=operacion.origen_id, id_empresa=operacion.id_empresa
    ).first()
    if nota is None:
        raise OperacionError("La NotaVenta vinculada no existe en esta empresa.")
    confirmar_nota_venta(nota, operacion.id_almacen, usuario)
