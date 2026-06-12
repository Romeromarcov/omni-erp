"""
Lógica de negocio para Cuentas por Cobrar.

registrar_abono()  — aplica un pago parcial o total a una CxC.
calcular_aging()   — clasifica el saldo vencido por tramos de días.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # BUILD-1: solo para anotaciones (evita F821)
    from .models import AbonoCxC



class AbonoError(Exception):
    pass


def _saldo_pendiente(cxc) -> Decimal:
    """Calcula el saldo restante de una CxC (monto - abonos)."""
    total_abonado = cxc.abonos.aggregate(t=Sum("monto"))["t"] or Decimal("0")
    return cxc.monto - total_abonado


@transaction.atomic
def registrar_abono(cxc, monto: Decimal, usuario, descripcion: str = "") -> "AbonoCxC":
    """
    Aplica un abono a una CxC y actualiza su estado.

    Args:
        cxc:         Instancia CuentaPorCobrar (select_for_update aplicado internamente).
        monto:       Monto del abono (positivo).
        usuario:     Instancia Usuarios que realiza el abono.
        descripcion: Nota opcional.

    Returns:
        Instancia AbonoCxC creada.

    Raises:
        AbonoError si el monto es inválido o la CxC está pagada.
    """
    from .models import AbonoCxC, CuentaPorCobrar

    monto = Decimal(str(monto))
    if monto <= 0:
        raise AbonoError("El monto del abono debe ser mayor a cero.")

    # Lock CxC para evitar doble abono concurrente
    cxc = CuentaPorCobrar.objects.select_for_update().get(pk=cxc.pk)

    if cxc.estado == "pagada":
        raise AbonoError("La cuenta ya está completamente pagada.")

    saldo = _saldo_pendiente(cxc)
    if monto > saldo:
        raise AbonoError(
            f"El abono ({monto}) excede el saldo pendiente ({saldo})."
        )

    abono = AbonoCxC.objects.create(
        cuenta_por_cobrar=cxc,
        monto=monto,
        usuario=usuario,
        descripcion=descripcion,
    )

    # Actualizar estado
    nuevo_saldo = saldo - monto
    if nuevo_saldo == 0:
        cxc.estado = "pagada"
    else:
        cxc.estado = "parcial"
    cxc.save(update_fields=["estado"])

    # Emitir evento
    from apps.core.events import CobranzaEvents, publish

    event_type = (
        CobranzaEvents.PAGO_TOTAL if nuevo_saldo == 0 else CobranzaEvents.PAGO_PARCIAL
    )
    publish(
        event_type=event_type,
        tenant_id=str(cxc.empresa_id) if hasattr(cxc, "empresa_id") else "unknown",
        payload={
            "cxc_id": str(cxc.pk),
            "cliente_id": cxc.cliente_ref,
            "monto_abono": str(monto),
            "saldo_restante": str(nuevo_saldo),
        },
        actor_id=str(usuario.pk),
    )

    return abono


def calcular_aging(empresa_id) -> dict:
    """
    Clasifica las CxC pendientes/vencidas de una empresa por tramos de días.

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
    from django.db.models import DecimalField
    from django.db.models.functions import Coalesce

    from .models import CuentaPorCobrar

    hoy = timezone.now().date()
    # BUG-M2: el saldo se anota en una sola consulta (Coalesce(Sum)) en vez de
    # un aggregate por instancia (N+1).
    cxc_qs = CuentaPorCobrar.objects.filter(
        empresa=empresa_id,
        estado__in=["pendiente", "parcial", "vencida"],
    ).annotate(
        total_abonado_agg=Coalesce(
            Sum("abonos__monto"),
            Decimal("0"),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )

    buckets: dict[str, dict[str, Any]] = {
        "corriente":   {"count": 0, "total": Decimal("0")},
        "dias_1_30":   {"count": 0, "total": Decimal("0")},
        "dias_31_60":  {"count": 0, "total": Decimal("0")},
        "dias_61_90":  {"count": 0, "total": Decimal("0")},
        "dias_90_mas": {"count": 0, "total": Decimal("0")},
    }

    for cxc in cxc_qs:
        saldo = cxc.monto - cxc.total_abonado_agg
        if saldo <= 0:
            continue
        dias_vencida = (hoy - cxc.fecha_vencimiento).days
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
