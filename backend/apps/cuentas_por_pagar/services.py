"""
Lógica de negocio para Cuentas por Pagar.

registrar_abono_cxp()  — aplica un pago parcial o total a una CxP.
calcular_aging_cxp()   — clasifica el saldo vencido por tramos de días.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # BUILD-1: solo para anotaciones (evita F821)
    from .models import AbonoCxP

logger = logging.getLogger(__name__)


class AbonoCxPError(Exception):
    pass


@transaction.atomic
def registrar_abono_cxp(
    cxp, monto: Decimal, usuario, descripcion: str = "", generar_asiento: bool = True,
    tasa_original: Decimal | None = None, tasa_pago: Decimal | None = None,
) -> "AbonoCxP":
    """
    Aplica un abono a una CxP y actualiza su estado.

    Args:
        generar_asiento: si True (default, flujo ``/abonar/``), postea el asiento
            ``PAGO_CXP``. Los flujos que llevan su PROPIO asiento del lado del
            pago (p. ej. pago de terceros Zelle → ``PAGO_TERCERO``) pasan False
            para no DUPLICAR el cargo a la CxP ni adelantar un AbonoCxPError que
            taparía el 422 del asiento real del flujo llamador.
        tasa_original: tasa a la que se reconoció la CxP (moneda base/divisa).
        tasa_pago:     tasa a la que se realiza el pago. Si ambas se dan y
            difieren, se registra la diferencia en cambio realizada y su asiento
            (GANANCIA_CAMBIARIA / PERDIDA_CAMBIARIA). Solo aplica cuando
            ``generar_asiento`` es True.

    Raises:
        AbonoCxPError si el monto es inválido o la CxP está pagada.
    """
    from .models import AbonoCxP, CuentaPorPagar

    monto = Decimal(str(monto))
    if monto <= 0:
        raise AbonoCxPError("El monto del abono debe ser mayor a cero.")

    cxp = CuentaPorPagar.objects.select_for_update().get(pk=cxp.pk)

    if cxp.estado == "PAGADA":
        raise AbonoCxPError("La cuenta ya está completamente pagada.")

    if cxp.estado == "ANULADA":
        raise AbonoCxPError("No se puede abonar a una CxP anulada.")

    if monto > cxp.monto_pendiente:
        raise AbonoCxPError(
            f"El abono ({monto}) excede el saldo pendiente ({cxp.monto_pendiente})."
        )

    abono = AbonoCxP.objects.create(
        cuenta_por_pagar=cxp,
        monto=monto,
        usuario=usuario,
        descripcion=descripcion,
    )

    nuevo_pendiente = cxp.monto_pendiente - monto
    cxp.monto_pendiente = nuevo_pendiente
    if nuevo_pendiente == 0:
        cxp.estado = "PAGADA"
    else:
        cxp.estado = "PARCIAL"
    cxp.save(update_fields=["monto_pendiente", "estado"])

    # R-CODE-11: el abono a una CxP genera su asiento ``PAGO_CXP`` (DR CxP /
    # CR Banco o Caja) en la MISMA transacción, con la política uniforme de
    # ``generar_asiento_o_fallar`` (espejo exacto de ``cuentas_por_cobrar``).
    # Antes los abonos a CxP NO generaban asiento (asimetría con CxC). Si la
    # empresa exige contabilidad y falta el mapeo, o el asiento descuadra,
    # ``AsientoError`` revierte el abono completo (la @transaction.atomic hace
    # rollback al propagar). Una empresa informal (sin contabilidad activa y sin
    # mapeo) procede sin asiento (R-PROD-3). Si el llamador lleva su propio
    # asiento (generar_asiento=False), se omite para no duplicar el cargo a CxP.
    if not generar_asiento:
        return abono

    from apps.contabilidad.services import AsientoError, generar_asiento_o_fallar

    try:
        generar_asiento_o_fallar("PAGO_CXP", abono, cxp.id_empresa, monto, usuario=usuario)
    except AsientoError as exc:
        logger.exception(
            "registrar_abono_cxp: asiento PAGO_CXP obligatorio falló | empresa=%s | cxp=%s",
            cxp.id_empresa_id,
            cxp.pk,
        )
        raise AbonoCxPError(
            "No se pudo generar el asiento contable obligatorio. "
            "Configure el Mapeo Contable de la empresa."
        ) from exc

    # Diferencia en cambio realizada (multi-tasa): si el pago se hace a una tasa
    # distinta de aquella a la que se reconoció la CxP, el valor en moneda base
    # del mismo monto en divisa cambia → ganancia/pérdida cambiaria.
    if tasa_original is not None and tasa_pago is not None:
        registrar_diferencia_cambiaria_cxp(
            abono, monto, tasa_original, tasa_pago, usuario=usuario
        )

    return abono


def registrar_diferencia_cambiaria_cxp(
    abono, monto: Decimal, tasa_original: Decimal, tasa_pago: Decimal, usuario=None
):
    """Registra la diferencia en cambio realizada de un abono a CxP y su asiento.

    Las tasas se cotizan como **unidades de moneda base por 1 unidad de divisa**
    (p. ej. Bs por USD): así ``monto_moneda × tasa`` da el valor en moneda base.
    Para un pasivo (CxP), si la divisa se encareció (``tasa_pago`` > original)
    pagar cuesta más en moneda base → PÉRDIDA; si se abarató → GANANCIA. Devuelve
    la ``DiferenciaCambiaria`` creada, o None si las tasas son iguales (sin
    diferencia). El asiento (GANANCIA_CAMBIARIA / PERDIDA_CAMBIARIA) sigue la
    política R-CODE-11; si la CxP no exige contabilidad y falta el mapeo, la
    diferencia se registra igual sin asiento (R-PROD-3).
    """
    from .models import DiferenciaCambiaria

    monto = Decimal(str(monto))
    tasa_original = Decimal(str(tasa_original))
    tasa_pago = Decimal(str(tasa_pago))
    # Tasas no positivas invertirían silenciosamente signo y magnitud (defensa en
    # profundidad: el endpoint ya valida, pero el servicio es invocable directo).
    if tasa_original <= 0 or tasa_pago <= 0:
        raise AbonoCxPError("Las tasas de cambio deben ser mayores a cero.")
    delta = tasa_pago - tasa_original
    if delta == 0:
        return None

    monto_diferencia = (monto * abs(delta)).quantize(Decimal("0.0001"))
    tipo = "PERDIDA" if delta > 0 else "GANANCIA"
    empresa = abono.cuenta_por_pagar.id_empresa

    diferencia = DiferenciaCambiaria.objects.create(
        id_empresa=empresa,
        id_abono_cxp=abono,
        monto_moneda=monto,
        tasa_original=tasa_original,
        tasa_pago=tasa_pago,
        monto_diferencia=monto_diferencia,
        tipo=tipo,
    )

    from apps.contabilidad.services import AsientoError, generar_asiento_o_fallar

    tipo_asiento = "PERDIDA_CAMBIARIA" if tipo == "PERDIDA" else "GANANCIA_CAMBIARIA"
    try:
        generar_asiento_o_fallar(
            tipo_asiento, diferencia, empresa, monto_diferencia, usuario=usuario
        )
    except AsientoError as exc:
        logger.exception(
            "registrar_diferencia_cambiaria_cxp: asiento %s falló | empresa=%s | abono=%s",
            tipo_asiento, empresa.pk, abono.pk,
        )
        raise AbonoCxPError(
            "No se pudo generar el asiento de diferencia cambiaria obligatorio. "
            "Configure el Mapeo Contable de la empresa."
        ) from exc

    return diferencia


def calcular_aging_cxp(empresa_id) -> dict:
    """
    Clasifica las CxP pendientes/vencidas de una empresa por tramos de días.

    Returns:
        {
            "corriente":    {"count": int, "total": Decimal},
            "dias_1_30":    {"count": int, "total": Decimal},
            "dias_31_60":   {"count": int, "total": Decimal},
            "dias_61_90":   {"count": int, "total": Decimal},
            "dias_90_mas":  {"count": int, "total": Decimal},
            "total_general": Decimal,
        }
    """
    from .models import CuentaPorPagar

    # localdate() = hoy en TIME_ZONE (America/Caracas), no en UTC: con
    # now().date() el aging de CxP se corría un día tras las 20:00 Caracas
    # (= 00:00 UTC) y clasificaba mal los tramos de vencimiento (espejo del
    # mismo fix en cuentas_por_cobrar).
    hoy = timezone.localdate()
    cxp_qs = CuentaPorPagar.objects.filter(
        id_empresa_id=empresa_id,
        estado__in=["PENDIENTE", "PARCIAL", "VENCIDA"],
        activo=True,
    )

    # Tipado explícito: sin la anotación, mypy infiere dict[str, object] y marca
    # las acumulaciones (+=) y el sum() final como errores [operator]/[misc].
    buckets: dict[str, dict[str, Any]] = {
        "corriente":   {"count": 0, "total": Decimal("0")},
        "dias_1_30":   {"count": 0, "total": Decimal("0")},
        "dias_31_60":  {"count": 0, "total": Decimal("0")},
        "dias_61_90":  {"count": 0, "total": Decimal("0")},
        "dias_90_mas": {"count": 0, "total": Decimal("0")},
    }

    for cxp in cxp_qs:
        saldo = cxp.monto_pendiente
        if saldo <= 0:
            continue
        dias_vencida = (hoy - cxp.fecha_vencimiento).days
        if dias_vencida <= 0:
            bucket = "corriente"
        elif dias_vencida <= 30:
            bucket = "dias_1_30"
        elif dias_vencida <= 60:
            bucket = "dias_31_60"
        elif dias_vencida <= 90:
            bucket = "dias_61_90"
        else:
            bucket = "dias_90_mas"
        buckets[bucket]["count"] += 1
        buckets[bucket]["total"] += saldo

    total_general = sum(b["total"] for b in buckets.values())
    return {**buckets, "total_general": total_general}
