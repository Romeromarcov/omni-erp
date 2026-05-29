"""
Config DSL por tenant para el módulo CxC.

Lee desde configuracion_motor.ParametroSistema y provee defaults seguros.

Claves usadas:
  cxc.datasource           → "native" | "odoo"
  cxc.enabled              → "true" | "false"
  cxc.agente_ia.enabled    → "true" | "false"
  cxc.fraccionamiento.enabled → "true" | "false"
  cxc.acuerdos.max_plazo_dias → int (default 365)
  cxc.tasas.moneda_display → "USD" | "VES"
  cxc.canales              → comma-separated list, e.g. "whatsapp,email,llamada"

Ejemplo de activación de un tenant:
    from apps.cxc.config import CxcConfig
    cfg = CxcConfig.para_empresa(empresa)
    if cfg.agente_ia_enabled:
        ...
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _get_param(empresa, codigo: str, default: str = "") -> str:
    """Lee un ParametroSistema para una empresa. Retorna default si no existe."""
    from apps.configuracion_motor.models import ParametroSistema

    try:
        param = ParametroSistema.objects.get(
            id_empresa=empresa,
            codigo_parametro=codigo,
            activo=True,
        )
        return param.valor_parametro.strip()
    except ParametroSistema.DoesNotExist:
        return default


def _to_bool(val: str) -> bool:
    return val.lower() in ("true", "1", "yes", "si", "sí")


@dataclass
class CxcConfig:
    """Configuración del módulo CxC para un tenant específico."""

    empresa: object  # core.Empresa instance

    # Datasource
    datasource: str = "native"       # "native" | "odoo"
    enabled: bool = True

    # Agente IA
    agente_ia_enabled: bool = False

    # Fraccionamiento (feature flag)
    fraccionamiento_enabled: bool = False

    # Acuerdos
    max_plazo_dias: int = 365

    # Tasas
    moneda_display: str = "USD"

    # Canales habilitados
    canales: list = field(default_factory=lambda: ["whatsapp", "email", "llamada", "visita", "carta"])

    @classmethod
    def para_empresa(cls, empresa) -> "CxcConfig":
        """
        Carga la configuración CxC de un tenant desde ParametroSistema.
        Todos los valores tienen defaults seguros si no están configurados.
        """
        datasource = _get_param(empresa, "cxc.datasource", "native")
        enabled = _to_bool(_get_param(empresa, "cxc.enabled", "true"))
        agente_ia = _to_bool(_get_param(empresa, "cxc.agente_ia.enabled", "false"))
        fraccionamiento = _to_bool(_get_param(empresa, "cxc.fraccionamiento.enabled", "false"))
        max_plazo = int(_get_param(empresa, "cxc.acuerdos.max_plazo_dias", "365") or "365")
        moneda = _get_param(empresa, "cxc.tasas.moneda_display", "USD")
        canales_raw = _get_param(empresa, "cxc.canales", "whatsapp,email,llamada,visita,carta")
        canales = [c.strip() for c in canales_raw.split(",") if c.strip()]

        return cls(
            empresa=empresa,
            datasource=datasource,
            enabled=enabled,
            agente_ia_enabled=agente_ia,
            fraccionamiento_enabled=fraccionamiento,
            max_plazo_dias=max_plazo,
            moneda_display=moneda,
            canales=canales,
        )

    def to_dict(self) -> dict:
        """Serializa la config a dict (para endpoints de diagnóstico)."""
        return {
            "datasource": self.datasource,
            "enabled": self.enabled,
            "agente_ia_enabled": self.agente_ia_enabled,
            "fraccionamiento_enabled": self.fraccionamiento_enabled,
            "max_plazo_dias": self.max_plazo_dias,
            "moneda_display": self.moneda_display,
            "canales": self.canales,
        }
