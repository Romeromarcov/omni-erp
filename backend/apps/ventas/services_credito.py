"""Evaluación de crédito real con consideración de abonos, AsignacionPago y días de gracia (Plan 09 §3.3)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q, Sum
from django.utils import timezone

_CERO = Decimal("0.00")


def _saldo_neto_cxc(cxc) -> Decimal:
    """Saldo abierto de una CxC descontando AbonoCxC y AsignacionPago activas no enlazadas a AbonoCxC."""
    from apps.cuentas_por_cobrar.models import AbonoCxC
    from apps.finanzas.models import AsignacionPago

    abonado = AbonoCxC.objects.filter(cuenta_por_cobrar=cxc).aggregate(total=Sum("monto"))["total"] or _CERO

    doc_json = cxc.documento_json if isinstance(cxc.documento_json, dict) else {}
    id_factura = doc_json.get("id_factura")
    filtro_asig = Q(id_cxc=cxc)
    if id_factura:
        filtro_asig = filtro_asig | Q(id_cxc__isnull=True, id_factura_venta_id=id_factura)

    asignado_extra = (
        AsignacionPago.objects.filter(
            id_empresa_id=cxc.empresa_id,
            estado="ACTIVA",
            activo=True,
            id_abono_cxc__isnull=True,
        )
        .filter(filtro_asig)
        .aggregate(total=Sum("monto_asignado_documento"))["total"]
        or _CERO
    )

    saldo = Decimal(str(cxc.monto)) - Decimal(str(abonado)) - Decimal(str(asignado_extra))
    return max(saldo, _CERO)


def evaluar_credito_cliente(
    cliente,
    empresa,
    monto_nuevo: Decimal | str | int = Decimal("0"),
    *,
    fecha: date | None = None,
) -> dict[str, Any]:
    """Evalúa saldo neto, mora real (descontando abonos/asignaciones y días de gracia) y límite de crédito."""
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar

    hoy = fecha or timezone.localdate()
    monto_adicional = Decimal(str(monto_nuevo or "0"))
    limite = Decimal(str(getattr(cliente, "limite_credito", 0) or "0"))
    dias_gracia = int(getattr(cliente, "dias_gracia_mora", 0) or 0)
    politica_bloqueo_mora = bool(getattr(cliente, "bloquear_por_mora", False))

    abiertas = list(
        CuentaPorCobrar.objects.filter(
            cliente=cliente,
            empresa=empresa,
            estado__in=["pendiente", "parcial", "vencida"],
        ).order_by("fecha_vencimiento")
    )

    saldo_pendiente = _CERO
    monto_vencido = _CERO
    cxc_vencidas = 0
    dias_mora_max = 0

    for cxc in abiertas:
        saldo = _saldo_neto_cxc(cxc)
        if saldo <= _CERO:
            continue
        saldo_pendiente += saldo
        limite_vencimiento = cxc.fecha_vencimiento + timedelta(days=dias_gracia)
        if hoy > limite_vencimiento:
            cxc_vencidas += 1
            monto_vencido += saldo
            dias_mora_max = max(dias_mora_max, (hoy - limite_vencimiento).days)

    disponible = max(limite - saldo_pendiente, _CERO) if limite > _CERO else None
    excede_limite = bool(limite > _CERO and (saldo_pendiente + monto_adicional) > limite)
    bloqueado_por_mora = bool(politica_bloqueo_mora and monto_vencido > _CERO)
    bloqueado = bloqueado_por_mora or excede_limite

    motivos = []
    if bloqueado_por_mora:
        motivos.append(
            f"Cliente con {cxc_vencidas} factura(s)/nota(s) vencida(s) por {monto_vencido:.2f} "
            f"(máx {dias_mora_max} días sobre {dias_gracia} días de gracia)."
        )
    if excede_limite:
        motivos.append(f"Excede el límite de crédito ({saldo_pendiente + monto_adicional:.2f} > {limite:.2f}).")

    return {
        "cliente_id": str(cliente.pk),
        "tipo_cliente": cliente.tipo_cliente,
        "limite_credito": limite,
        "dias_gracia_mora": dias_gracia,
        "saldo_pendiente": saldo_pendiente,
        "credito_disponible": disponible,
        "monto_vencido": monto_vencido,
        "cxc_vencidas": cxc_vencidas,
        "dias_mora_max": dias_mora_max,
        "politica_bloqueo_mora": politica_bloqueo_mora,
        "bloqueado_por_mora": bloqueado_por_mora,
        "excede_limite": excede_limite,
        "bloqueado": bloqueado,
        "motivo_bloqueo": " ".join(motivos),
    }
