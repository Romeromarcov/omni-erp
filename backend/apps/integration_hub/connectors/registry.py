"""
ConnectorRegistry — Registro global de conectores disponibles.

Cada conector se registra al arrancar la app (en apps.py).
El SyncEngine usa el registry para obtener la clase correcta
dado el código del proveedor.

Uso:
    from apps.integration_hub.connectors.registry import registry

    # Registrar (en apps.py)
    registry.register(OdooConnector)

    # Obtener instancia
    connector = registry.get_connector(instancia)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Type

from apps.integration_hub.connectors.base import BaseConnector, ConnectorError

if TYPE_CHECKING:
    from apps.integration_hub.models import ConectorInstancia

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Registro singleton de todos los conectores disponibles."""

    def __init__(self):
        self._registry: dict[str, Type[BaseConnector]] = {}

    def register(self, connector_class: Type[BaseConnector]) -> None:
        """
        Registra una clase de conector.
        Lanza ValueError si el PROVIDER_CODE está vacío o ya registrado.
        """
        code = connector_class.PROVIDER_CODE
        if not code:
            raise ValueError(
                f"El conector {connector_class.__name__} no tiene PROVIDER_CODE definido."
            )
        if code in self._registry:
            logger.warning(
                "Conector '%s' ya registrado — sobreescribiendo con %s",
                code,
                connector_class.__name__,
            )
        self._registry[code] = connector_class
        logger.info("Conector registrado: %s (%s)", connector_class.PROVIDER_NAME, code)

    def get_class(self, provider_code: str) -> Type[BaseConnector] | None:
        """Retorna la clase del conector o None si no está registrado."""
        return self._registry.get(provider_code)

    def get_connector(self, instancia: "ConectorInstancia") -> BaseConnector:
        """
        Crea y retorna una instancia del conector para la instancia dada.
        Lanza ConnectorError si el proveedor no está registrado.
        """
        code = instancia.id_proveedor.codigo
        cls = self._registry.get(code)
        if cls is None:
            raise ConnectorError(
                f"No hay conector registrado para el proveedor '{code}'. "
                f"Proveedores disponibles: {list(self._registry.keys())}"
            )
        return cls(instancia)

    def list_registered(self) -> list[str]:
        """Retorna lista de códigos de proveedores registrados."""
        return list(self._registry.keys())


# Instancia global (singleton)
registry = ConnectorRegistry()
