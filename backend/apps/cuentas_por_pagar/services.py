"""
Lógica de negocio para Cuentas por Pagar.

registrar_abono_cxp()  — aplica un pago parcial o total a una CxP.
calcular_aging_cxp()   — clasifica el saldo vencido por tramos de días.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # BUILD-1: solo para anotaciones (evita F821)
    from .models import AbonoCxP



class AbonoCxPError(Exception):
    pass


@transaction.atomic
def registrar_abono_cxp(cxp, monto: Decimal, usuario, descripcion: str = "") -> "AbonoCxP":
    """
    Aplica un abono a una CxP y actualiza su estado.

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

    return abono


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
