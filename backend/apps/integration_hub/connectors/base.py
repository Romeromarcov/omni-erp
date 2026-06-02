"""
BaseConnector — Interfaz abstracta para todos los conectores del Integration Hub.

Cada conector concreto (Odoo, SAP, Shopify, etc.) hereda de esta clase
e implementa los métodos de su capacidad.

Convenciones:
- pull_*  → trae datos del sistema externo hacia Omni (inbound)
- push_*  → envía datos de Omni al sistema externo (outbound)
- Cada método retorna dicts normalizados (no los objetos nativos del sistema externo)
- Los métodos de lectura NUNCA deben modificar el sistema externo
- Errores de conexión: levantar ConnectorConnectionError
- Errores de datos: levantar ConnectorDataError
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.integration_hub.models import ConectorInstancia

logger = logging.getLogger(__name__)


# ── Excepciones ──────────────────────────────────────────────────────────────

class ConnectorError(Exception):
    """Base para todos los errores de conectores."""


class ConnectorConnectionError(ConnectorError):
    """Error al conectar o autenticar con el sistema externo."""


class ConnectorDataError(ConnectorError):
    """Error al leer o escribir datos (campo faltante, formato incorrecto, etc.)."""


class ConnectorNotSupportedError(ConnectorError):
    """La operación solicitada no está soportada por este conector."""


# ── Resultados normalizados ───────────────────────────────────────────────────

@dataclass
class TestConnectionResult:
    success: bool
    message: str
    version: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class SyncResult:
    tipo_entidad: str
    total: int = 0
    creados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    fallidos: int = 0
    errores: list = field(default_factory=list)

    @property
    def exitoso(self) -> bool:
        return self.fallidos == 0

    def agregar_error(self, id_externo: str, mensaje: str):
        if len(self.errores) < 100:
            self.errores.append({"id": id_externo, "error": mensaje})
        self.fallidos += 1


# ── Clase base abstracta ──────────────────────────────────────────────────────

class BaseConnector(ABC):
    """
    Interfaz base que todos los conectores deben implementar.

    Atributos de clase obligatorios:
        PROVIDER_CODE (str): código único del proveedor ("odoo", "sap_b1", etc.)
        PROVIDER_NAME (str): nombre humano ("Odoo", "SAP Business One", etc.)
        SUPPORTED_ENTITIES (list[str]): entidades que soporta este conector
    """

    PROVIDER_CODE: str = ""
    PROVIDER_NAME: str = ""
    SUPPORTED_ENTITIES: list[str] = []

    def __init__(self, instancia: "ConectorInstancia"):
        self.instancia = instancia
        self._config = instancia.get_config()
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    # ── Conexión ──────────────────────────────────────────────────────────────

    @abstractmethod
    def test_connection(self) -> TestConnectionResult:
        """
        Verifica que las credenciales y la conexión son válidas.
        Debe ser idempotente (solo leer, nunca modificar).
        """

    @abstractmethod
    def get_version_info(self) -> dict:
        """Retorna información de versión del sistema externo."""

    # ── Lectura (pull) ────────────────────────────────────────────────────────

    def pull_contactos(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        """
        Trae contactos (clientes/proveedores) del sistema externo.
        Retorna lista de dicts normalizados con claves estándar.
        """
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta sync de contactos"
        )

    def pull_productos(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        """Trae productos del sistema externo."""
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta sync de productos"
        )

    def pull_pedidos_venta(self, desde: datetime | None = None, limite: int = 200) -> list[dict]:
        """Trae pedidos de venta del sistema externo."""
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta sync de pedidos de venta"
        )

    def pull_pedidos_compra(self, desde: datetime | None = None, limite: int = 200) -> list[dict]:
        """Trae órdenes de compra del sistema externo."""
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta sync de pedidos de compra"
        )

    def pull_facturas_venta(self, desde: datetime | None = None, limite: int = 200) -> list[dict]:
        """Trae facturas de venta del sistema externo."""
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta sync de facturas de venta"
        )

    def pull_pagos(self, desde: datetime | None = None, limite: int = 300) -> list[dict]:
        """Trae pagos del sistema externo."""
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta sync de pagos"
        )

    def pull_inventario(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        """Trae movimientos o niveles de inventario del sistema externo."""
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta sync de inventario"
        )

    # ── Escritura (push) ──────────────────────────────────────────────────────

    def push_contacto(self, datos: dict) -> str:
        """
        Crea o actualiza un contacto en el sistema externo.
        Retorna el ID externo creado/actualizado.
        """
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta push de contactos"
        )

    def push_producto(self, datos: dict) -> str:
        """Crea o actualiza un producto en el sistema externo."""
        raise ConnectorNotSupportedError(
            f"{self.PROVIDER_NAME} no soporta push de productos"
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    def supports(self, entidad: str) -> bool:
        """Verifica si este conector soporta una entidad."""
        return entidad in self.SUPPORTED_ENTITIES

    def normalizar_contacto(self, raw: dict) -> dict:
        """
        Override para transformar el dict nativo a formato Omni.
        Por defecto retorna el dict tal como está.
        """
        return raw

    def normalizar_producto(self, raw: dict) -> dict:
        """Override para transformar producto nativo a formato Omni."""
        return raw

    def _safe_str(self, value: Any, field_name: str = "") -> str:
        """Convierte un valor a string de forma segura."""
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return str(value[1]) if len(value) > 1 else str(value[0]) if value else ""
        return str(value)

    def _safe_float(self, value: Any) -> float:
        """Convierte un valor a float de forma segura. SOLO para campos NO monetarios."""
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _safe_decimal(self, value: Any):
        """
        Convierte un valor a Decimal de forma segura (R-CODE-4 / H-BUG-3).

        Usar SIEMPRE para campos monetarios (precios, montos, saldos). Pasa por
        str() para no heredar el error binario de un float intermedio.
        """
        from decimal import Decimal, InvalidOperation

        if value in (None, "", False):
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    def _safe_int(self, value: Any) -> int:
        """Convierte un valor a int de forma segura."""
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
