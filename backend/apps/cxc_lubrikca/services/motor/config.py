"""Configuración del motor determinístico (port puro, sin env-loading).

Estas dataclasses son el contrato de configuración del motor. A diferencia del
proyecto fuente CxC_Lubrikca, NO leen variables de entorno: los defaults se
declaran aquí y el bridge Django (Fase 3) las construye desde la config del
tenant. Mantener Django-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class EngineConfig:
    cash_window_business_days: int = 3
    bcv_complete_formula: str = "differential_over_binance"
    lista_usd: str = "USD"
    lista_bcv: str = "BCV"


@dataclass(frozen=True)
class ReconciliationConfig:
    tolerance_rounding: Decimal = Decimal("0.01")
    tolerance_red: Decimal = Decimal("1.00")


@dataclass(frozen=True)
class HourAuditConfig:
    threshold_minutes: int = 60
    rate_swing_pct: Decimal = Decimal("0.03")


def default_engine_config() -> EngineConfig:
    return EngineConfig()


def default_reconciliation_config() -> ReconciliationConfig:
    return ReconciliationConfig()


def default_hour_audit_config() -> HourAuditConfig:
    return HourAuditConfig()
