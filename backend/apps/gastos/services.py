"""
Lógica de negocio del módulo de Gastos (R-CODE-11 en la aprobación).

Flujo:
  aprobar_gasto()  → valida respaldo (factura), transiciona a APROBADO/CONTABILIZADO
                     y genera el/los asiento(s) contables:
                       GASTO     → DR Cuenta Gasto  / CR CxP o Banco   (base sin IVA)
                       GASTO_IVA → DR IVA Crédito    / CR CxP o Banco   (porción IVA)
  rechazar_gasto() → transiciona a RECHAZADO.

El crédito (CxP o Banco) lo decide el `MapeoContable` del tenant (cuenta_haber),
no este servicio: una empresa que difiere el pago mapea CxP; una que paga al
contado mapea Banco/Caja. Espejo de `ventas.services.confirmar_nota_venta` y de
`compras.services.registrar_factura_compra`.
"""

import logging
from decimal import Decimal

from django.db import transaction

from apps.contabilidad.services import AsientoError, generar_asiento_o_fallar

logger = logging.getLogger(__name__)


class GastoError(Exception):
    pass


def aprobar_gasto(gasto, usuario=None) -> dict:
    """
    Aprueba un gasto pendiente y genera su(s) asiento(s) contable(s).

    Reglas de respaldo (spec Gastos):
      - Si la categoría exige factura (``requiere_factura``) y el gasto no la
        tiene (``tiene_factura=False``) → se bloquea la aprobación.
      - Si el gasto no tiene factura (y la categoría no la exige) → se aprueba
        igual pero se marca ``sin_respaldo=True`` (gasto sin soporte documental).

    Args:
        gasto:   Instancia Gasto en estado PENDIENTE_APROBACION.
        usuario: Usuarios que aprueba (trazabilidad del asiento). Opcional.

    Returns:
        {"gasto": Gasto, "asiento": AsientoContable|None,
         "asiento_iva": AsientoContable|None}

    Raises:
        GastoError: estado inválido, falta de factura obligatoria, período
                    cerrado o fallo del asiento obligatorio.
    """
    from apps.gastos.models import Gasto

    # Pre-chequeo SIN lock para el gate de aprobación: ``crear_solicitud``
    # confirma su propia transacción y debe sobrevivir al ``raise`` (si estuviera
    # dentro de la atomic de contabilización, el raise la revertiría). La
    # contabilización con lock vive en ``_contabilizar_gasto``.
    gasto = Gasto.objects.select_related("id_categoria_gasto", "id_empresa").get(pk=gasto.pk)

    if gasto.estado_gasto != "PENDIENTE_APROBACION":
        raise GastoError(
            f"Solo se aprueban gastos PENDIENTE_APROBACION. Estado: {gasto.estado_gasto}"
        )

    categoria = gasto.id_categoria_gasto
    if getattr(categoria, "requiere_factura", False) and not gasto.tiene_factura:
        raise GastoError(
            "La categoría exige factura de respaldo: adjunte la factura antes de aprobar."
        )

    empresa = gasto.id_empresa

    # Reglas de aprobación configurables (T03): si el monto supera el umbral del
    # tenant (gestion_aprobaciones tipo GASTO), la aprobación se bloquea hasta que
    # la SolicitudAprobacion quede APROBADA.
    from apps.gestion_aprobaciones.services import (
        crear_solicitud,
        esta_aprobada,
        requiere_aprobacion,
    )

    if requiere_aprobacion(empresa, "GASTO", gasto.monto) and not esta_aprobada(gasto):
        crear_solicitud(gasto, empresa, usuario, "GASTO", gasto.monto)
        raise GastoError(
            "El gasto supera el umbral y requiere aprobación. Se registró la "
            "solicitud; un aprobador debe resolverla antes de aprobar el gasto."
        )

    return _contabilizar_gasto(gasto, usuario)


@transaction.atomic
def _contabilizar_gasto(gasto, usuario=None) -> dict:
    """Contabiliza un gasto ya autorizado, bajo lock pesimista. Separado de
    ``aprobar_gasto`` para que el gate de aprobación (que crea la solicitud y
    lanza) no comparta la transacción que aquí se confirma."""
    from apps.gastos.models import Gasto

    # Lock para evitar doble aprobación concurrente; re-valida bajo lock.
    gasto = Gasto.objects.select_for_update().select_related(
        "id_categoria_gasto", "id_empresa"
    ).get(pk=gasto.pk)
    if gasto.estado_gasto != "PENDIENTE_APROBACION":
        raise GastoError(
            f"Solo se aprueban gastos PENDIENTE_APROBACION. Estado: {gasto.estado_gasto}"
        )
    empresa = gasto.id_empresa

    # Enforcement de cierre de período fiscal: la aprobación postea un asiento.
    from apps.fiscal.services import PeriodoCerradoError, validar_periodo_abierto

    try:
        validar_periodo_abierto(empresa, gasto.fecha_gasto)
    except PeriodoCerradoError as exc:
        raise GastoError(str(exc)) from exc

    # Marca de gasto sin soporte documental (no bloquea, pero queda registrado).
    gasto.sin_respaldo = not gasto.tiene_factura
    gasto.estado_gasto = "APROBADO"

    monto_total = Decimal(str(gasto.monto))
    monto_iva = Decimal(str(gasto.monto_iva or 0))
    monto_base = monto_total - monto_iva
    if monto_base < 0:
        raise GastoError(
            f"La base del gasto (monto - IVA = {monto_base}) no puede ser negativa: "
            "el IVA no puede exceder el monto total."
        )
    if monto_total <= 0:
        raise GastoError(f"El monto del gasto debe ser mayor a cero. Obtenido: {monto_total}")

    # Si el gasto tiene líneas de imputación (DetalleGasto), deben reconciliar con
    # el encabezado: el asiento se postea desde el encabezado, así que una
    # divergencia silenciosa entre líneas y total sería un descuadre de imputación.
    detalles = list(gasto.detalles.all())
    if detalles:
        suma_detalles = sum(
            (Decimal(str(d.monto)) + Decimal(str(d.monto_iva or 0)) for d in detalles),
            Decimal("0"),
        )
        if suma_detalles != monto_total:
            raise GastoError(
                f"Las líneas del gasto ({suma_detalles}) no reconcilian con el "
                f"monto del encabezado ({monto_total})."
            )

    # R-CODE-11 centralizado. Si la empresa exige contabilidad y falta el mapeo,
    # AsientoError revierte toda la transacción (la aprobación no queda a medias).
    # Cada porción se postea solo si es > 0: un gasto 100% IVA (base 0) genera
    # únicamente el asiento GASTO_IVA, simétrico al caso sin IVA (solo GASTO).
    asiento = None
    asiento_iva = None
    try:
        if monto_base > 0:
            asiento, _ = generar_asiento_o_fallar("GASTO", gasto, empresa, monto_base, usuario=usuario)
        if monto_iva > 0:
            asiento_iva, _ = generar_asiento_o_fallar(
                "GASTO_IVA", gasto, empresa, monto_iva, usuario=usuario
            )
    except AsientoError as exc:
        raise GastoError(f"Error generando asiento del gasto: {exc}") from exc

    # Si se generó algún asiento (base o IVA), el gasto queda contabilizado.
    if asiento is not None or asiento_iva is not None:
        gasto.estado_gasto = "CONTABILIZADO"

    gasto.save(update_fields=["estado_gasto", "sin_respaldo"])

    logger.info(
        "Gasto aprobado | empresa=%s | gasto=%s | estado=%s | sin_respaldo=%s",
        empresa.pk, gasto.pk, gasto.estado_gasto, gasto.sin_respaldo,
    )

    return {"gasto": gasto, "asiento": asiento, "asiento_iva": asiento_iva}


@transaction.atomic
def rechazar_gasto(gasto, usuario=None, motivo: str = "") -> dict:
    """Rechaza un gasto pendiente. No genera asiento."""
    from apps.gastos.models import Gasto

    gasto = Gasto.objects.select_for_update().get(pk=gasto.pk)
    if gasto.estado_gasto != "PENDIENTE_APROBACION":
        raise GastoError(
            f"Solo se rechazan gastos PENDIENTE_APROBACION. Estado: {gasto.estado_gasto}"
        )
    gasto.estado_gasto = "RECHAZADO"
    gasto.save(update_fields=["estado_gasto"])
    logger.info("Gasto rechazado | gasto=%s | motivo=%s", gasto.pk, motivo or "—")
    return {"gasto": gasto}
