"""
Aging de cartera — representación canónica agnóstica al origen.

PartidaCartera: dataclass que normaliza tanto CuentaPorCobrar nativo
como dicts del Integration Hub (Odoo vía pull_cartera_vencida).

Bucket names: al_dia / 1_30 / 31_60 / 61_90 / mas_90
(Note: el calcular_aging() original en services.py usa nombres diferentes
 — este es el nuevo estándar para el módulo cxc)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

BUCKETS = ["al_dia", "1_30", "31_60", "61_90", "mas_90"]


def _calcular_bucket(dias: int) -> str:
    if dias <= 0:
        return "al_dia"
    if dias <= 30:
        return "1_30"
    if dias <= 60:
        return "31_60"
    if dias <= 90:
        return "61_90"
    return "mas_90"


@dataclass
class PartidaCartera:
    """
    Representación canónica agnóstica al origen (Omni nativo u Odoo via Hub).
    Calcula dias_vencida, vencida y bucket automáticamente en __post_init__.
    """
    cliente_id: str
    cliente_nombre: str
    orden_ref: str
    monto_total: Decimal
    monto_pendiente: Decimal
    fecha_vencimiento: Optional[date]
    estado_pago: str
    # Calculados automáticamente
    dias_vencida: int = field(init=False)
    vencida: bool = field(init=False)
    bucket: str = field(init=False)

    def __post_init__(self):
        hoy = date.today()
        if self.fecha_vencimiento:
            self.dias_vencida = (hoy - self.fecha_vencimiento).days
        else:
            self.dias_vencida = 0
        self.vencida = self.dias_vencida > 0
        self.bucket = _calcular_bucket(self.dias_vencida)

        # Normalizar Decimal
        if not isinstance(self.monto_total, Decimal):
            self.monto_total = Decimal(str(self.monto_total or 0))
        if not isinstance(self.monto_pendiente, Decimal):
            self.monto_pendiente = Decimal(str(self.monto_pendiente or 0))

    @classmethod
    def from_omni(cls, cxc) -> "PartidaCartera":
        """Construye desde CuentaPorCobrar nativo de Omni."""
        from django.db.models import Sum
        total_abonado = cxc.abonos.aggregate(t=Sum("monto"))["t"] or Decimal("0")
        saldo = cxc.monto - total_abonado

        cliente_nombre = ""
        if hasattr(cxc, "cliente") and cxc.cliente:
            cliente_nombre = getattr(cxc.cliente, "razon_social", str(cxc.cliente))

        return cls(
            cliente_id=str(cxc.cliente_id),
            cliente_nombre=cliente_nombre,
            orden_ref=cxc.referencia_externa or str(cxc.pk),
            monto_total=cxc.monto,
            monto_pendiente=saldo,
            fecha_vencimiento=cxc.fecha_vencimiento,
            estado_pago=cxc.estado,
        )

    @classmethod
    def from_hub_dict(cls, d: dict) -> "PartidaCartera":
        """Construye desde dict normalizado del Hub (pull_cartera_vencida)."""
        from datetime import datetime

        fecha_vcto = None
        raw_fecha = d.get("fecha_vencimiento")
        if raw_fecha:
            try:
                if isinstance(raw_fecha, str):
                    fecha_vcto = datetime.strptime(raw_fecha[:10], "%Y-%m-%d").date()
                elif isinstance(raw_fecha, date):
                    fecha_vcto = raw_fecha
            except ValueError:
                pass

        return cls(
            cliente_id=str(d.get("cliente_id", "")),
            cliente_nombre=str(d.get("cliente_nombre", "")),
            orden_ref=str(d.get("orden_ref", "")),
            monto_total=Decimal(str(d.get("monto_total", 0))),
            monto_pendiente=Decimal(str(d.get("monto_pendiente", 0))),
            fecha_vencimiento=fecha_vcto,
            estado_pago=str(d.get("estado_pago", "")),
        )


def calcular_aging(partidas: list[PartidaCartera]) -> dict:
    """
    Resumen ejecutivo de cartera por bucket de aging.

    Returns:
        {
            "buckets": {
                "al_dia":  {"count": int, "total": str},
                "1_30":    {"count": int, "total": str},
                "31_60":   {"count": int, "total": str},
                "61_90":   {"count": int, "total": str},
                "mas_90":  {"count": int, "total": str},
            },
            "total_pendiente": str,
            "total_partidas": int,
            "partidas_vencidas": int,
        }
    """
    buckets: dict[str, dict] = {
        b: {"count": 0, "total": Decimal("0")} for b in BUCKETS
    }

    total_pendiente = Decimal("0")
    partidas_vencidas = 0

    for p in partidas:
        if p.monto_pendiente <= 0:
            continue
        buckets[p.bucket]["count"] += 1
        buckets[p.bucket]["total"] += p.monto_pendiente
        total_pendiente += p.monto_pendiente
        if p.vencida:
            partidas_vencidas += 1

    return {
        "buckets": {k: {"count": v["count"], "total": str(v["total"])} for k, v in buckets.items()},
        "total_pendiente": str(total_pendiente),
        "total_partidas": len(partidas),
        "partidas_vencidas": partidas_vencidas,
    }
