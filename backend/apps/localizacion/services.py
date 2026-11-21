"""
Resolución de localización por empresa (ADR-007).

``get_localizacion(empresa)`` devuelve los 6 puertos aplicables según el país
de la empresa y sus flags de capa. Si una capa está desactivada o el país no
tiene localización registrada, devuelve implementaciones ``NoOp`` uniformes.
"""

from __future__ import annotations

from typing import Any

from . import ports, registry

PUERTOS_LEGAL_NOOP: dict[str, type[Any]] = {
    "MotorImpuestos": ports.MotorImpuestosNoOp,
    "GeneradorDocumentoLegal": ports.GeneradorDocumentoLegalNoOp,
    "CalculadoraNomina": ports.CalculadoraNominaNoOp,
    "LibroLegal": ports.LibroLegalNoOp,
}

PUERTOS_MERCADO_NOOP: dict[str, type[Any]] = {
    "ProveedorTasas": ports.ProveedorTasasNoOp,
    "MetodosPagoLocales": ports.MetodosPagoLocalesNoOp,
}

_NOOP_CLASSES: tuple[type[Any], ...] = tuple(PUERTOS_LEGAL_NOOP.values()) + tuple(PUERTOS_MERCADO_NOOP.values())


def get_localizacion(empresa) -> dict[str, Any]:
    """
    Devuelve ``{nombre_puerto: implementación}`` con los 6 puertos para la empresa.

    - Si la empresa no tiene país registrado: devuelve los 6 ``NoOp``.
    - Si ``localizacion_legal_activa`` es ``False``: los 4 puertos legales son ``NoOp``.
    - Si ``localizacion_mercado_activa`` es ``False``: los 2 puertos de mercado son ``NoOp``.
    """
    pais = getattr(empresa, "pais_codigo_iso", None)
    registrados = dict(registry.get(pais) or {})

    legal_activa = bool(getattr(empresa, "localizacion_legal_activa", True))
    mercado_activa = bool(getattr(empresa, "localizacion_mercado_activa", True))

    resultado: dict[str, Any] = {}
    for nombre, noop_cls in PUERTOS_LEGAL_NOOP.items():
        impl = registrados.get(nombre) if legal_activa else None
        resultado[nombre] = impl if impl is not None else noop_cls()

    for nombre, noop_cls in PUERTOS_MERCADO_NOOP.items():
        impl = registrados.get(nombre) if mercado_activa else None
        resultado[nombre] = impl if impl is not None else noop_cls()

    return resultado


def resumen_localizacion(empresa) -> dict[str, Any]:
    """
    Construye un resumen serializable del estado de localización de ``empresa``
    para consumo compartido entre la capa REST y MCP (sin duplicar lógica).
    """
    pais_raw = getattr(empresa, "pais_codigo_iso", None)
    pais_normalizado = registry.normalizar_codigo_pais(pais_raw)
    legal_activa = bool(getattr(empresa, "localizacion_legal_activa", True))
    mercado_activa = bool(getattr(empresa, "localizacion_mercado_activa", True))

    loc = get_localizacion(empresa)
    puertos_info: dict[str, dict[str, Any]] = {}
    for nombre, impl in loc.items():
        es_noop = isinstance(impl, _NOOP_CLASSES)
        puertos_info[nombre] = {
            "clase": impl.__class__.__name__,
            "es_noop": es_noop,
            "activo": not es_noop,
        }

    return {
        "pais_codigo_iso": pais_raw,
        "pais_normalizado": pais_normalizado,
        "localizacion_legal_activa": legal_activa,
        "localizacion_mercado_activa": mercado_activa,
        "puertos": puertos_info,
    }
