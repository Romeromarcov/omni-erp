"""Motor multi-tenant de ingesta, validación, clasificación y consolidación de extractos bancarios."""

from .modelos_canonicos import ExtractoBancarioError
from .parsers import FORMATOS_BANCO_SOPORTADOS, inferir_formato_banco
from .servicio_ingesta import (
    consolidar_saldos_extractos,
    desactivar_extracto_bancario,
    importar_extracto_bancario,
    preparar_extracto,
    serializar_consolidado,
)

__all__ = [
    "ExtractoBancarioError",
    "FORMATOS_BANCO_SOPORTADOS",
    "consolidar_saldos_extractos",
    "desactivar_extracto_bancario",
    "importar_extracto_bancario",
    "inferir_formato_banco",
    "preparar_extracto",
    "serializar_consolidado",
]
