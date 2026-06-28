"""Motor determinístico de CxC (port puro de CxC_Lubrikca).

Paquete Django-free: opera sobre las dataclasses internas del motor (su propio
contrato de datos), no sobre modelos Django. El bridge desde la configuración
Django/Odoo hacia estas dataclasses se construye en Fase 3.

Superficie pública del motor.
"""

from __future__ import annotations

from .business_days import (
    es_dia_habil,
    fin_ventana_contado,
    sumar_dias_habiles,
)
from .config import (
    EngineConfig,
    HourAuditConfig,
    ReconciliationConfig,
    default_engine_config,
    default_hour_audit_config,
    default_reconciliation_config,
)
from .decimal_utils import q2, q6, to_decimal
from .discounts import EngineInputs, calcular_factura
from .effective_dating import (
    descuento_vigente,
    promocion_primera_compra_vigente,
    regla_recurrencia_vigente,
    tasa_bcv_completo_vigente,
)
from .equivalents import (
    Equivalentes,
    calcular_equivalentes,
    congelar_en_vinculacion,
    es_ruta_bcv_pura,
    valor_pagado_usd,
)
from .hour_audit import (
    AuditFinding,
    BankMovement,
    HourAuditor,
    Prioridad,
    RateLookup,
)
from .models import (
    BandejaFacturacion,
    Cliente,
    Conciliacion,
    Condicion,
    DescuentoAplicado,
    DescuentoBCVCompleto,
    DescuentoMarcaCategoria,
    EstadoBandeja,
    EstadoVinculacion,
    Feriado,
    LineaOrden,
    MetodoPago,
    Moneda,
    OrdenVenta,
    Pago,
    PromocionPrimeraCompra,
    ReglaRecurrencia,
    ResultadoConciliacion,
    SerieTasa,
    TipoBeneficio,
    TipoDescuento,
    TipoFeriado,
    TipoTasa,
    Vinculacion,
)
from .price_resolver import DictPriceResolver, PriceResolver
from .reconcile import clasificar_diferencia

__all__ = [
    # business_days
    "es_dia_habil",
    "fin_ventana_contado",
    "sumar_dias_habiles",
    # config
    "EngineConfig",
    "HourAuditConfig",
    "ReconciliationConfig",
    "default_engine_config",
    "default_hour_audit_config",
    "default_reconciliation_config",
    # decimal_utils
    "q2",
    "q6",
    "to_decimal",
    # discounts
    "EngineInputs",
    "calcular_factura",
    # effective_dating
    "descuento_vigente",
    "promocion_primera_compra_vigente",
    "regla_recurrencia_vigente",
    "tasa_bcv_completo_vigente",
    # equivalents
    "Equivalentes",
    "calcular_equivalentes",
    "congelar_en_vinculacion",
    "es_ruta_bcv_pura",
    "valor_pagado_usd",
    # hour_audit
    "AuditFinding",
    "BankMovement",
    "HourAuditor",
    "Prioridad",
    "RateLookup",
    # models (dataclasses + enums)
    "BandejaFacturacion",
    "Cliente",
    "Conciliacion",
    "Condicion",
    "DescuentoAplicado",
    "DescuentoBCVCompleto",
    "DescuentoMarcaCategoria",
    "EstadoBandeja",
    "EstadoVinculacion",
    "Feriado",
    "LineaOrden",
    "MetodoPago",
    "Moneda",
    "OrdenVenta",
    "Pago",
    "PromocionPrimeraCompra",
    "ReglaRecurrencia",
    "ResultadoConciliacion",
    "SerieTasa",
    "TipoBeneficio",
    "TipoDescuento",
    "TipoFeriado",
    "TipoTasa",
    "Vinculacion",
    # price_resolver
    "DictPriceResolver",
    "PriceResolver",
    # reconcile
    "clasificar_diferencia",
]
