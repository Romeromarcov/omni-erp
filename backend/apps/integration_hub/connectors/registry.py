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
        Resolución de la clase, en orden:
        1. Registro estático (``register`` en apps.py) por código de proveedor.
        2. Carga **dinámica** (Fase 3): si el ``ConectorProveedor`` define
           ``clase_conector`` (ruta dotted), se importa, valida y cachea sin
           re-desplegar — permite reutilizar un conector genérico para varios
           proveedores.

        Lanza ConnectorError si no hay clase resoluble.
        """
        proveedor = instancia.id_proveedor
        code = proveedor.codigo
        cls = self._registry.get(code) or self._cargar_dinamico(proveedor)
        if cls is None:
            raise ConnectorError(
                f"No hay conector registrado para el proveedor '{code}'. "
                f"Proveedores disponibles: {list(self._registry.keys())}"
            )
        return cls(instancia)

    def _cargar_dinamico(self, proveedor) -> Type[BaseConnector] | None:
        """
        Carga la clase del conector desde ``proveedor.clase_conector`` (Fase 3).

        Valida que sea un ``BaseConnector`` y la cachea bajo el **código del
        proveedor** (no bajo ``PROVIDER_CODE`` de la clase), para que un mismo
        conector genérico pueda servir a varios proveedores. Retorna None si el
        proveedor no define ``clase_conector``.

        Lanza ConnectorError si la ruta no importa o no es un BaseConnector.
        """
        from django.utils.module_loading import import_string

        ruta = (getattr(proveedor, "clase_conector", "") or "").strip()
        if not ruta:
            return None

        try:
            cls = import_string(ruta)
        except ImportError as exc:
            raise ConnectorError(
                f"No se pudo importar la clase '{ruta}' del proveedor "
                f"'{proveedor.codigo}': {exc}"
            ) from exc

        if not (isinstance(cls, type) and issubclass(cls, BaseConnector)):
            raise ConnectorError(
                f"La clase '{ruta}' del proveedor '{proveedor.codigo}' no es un "
                f"BaseConnector."
            )

        self._registry[proveedor.codigo] = cls
        logger.info(
            "Conector cargado dinámicamente: %s → %s", proveedor.codigo, ruta
        )
        return cls

    def list_registered(self) -> list[str]:
        """Retorna lista de códigos de proveedores registrados."""
        return list(self._registry.keys())


# Instancia global (singleton)
registry = ConnectorRegistry()
