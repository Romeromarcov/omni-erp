"""
Registro de localizaciones (ADR-007).

Cada localización se registra por código ISO de país con las implementaciones
de los puertos que provee. El núcleo nunca importa las localizaciones
directamente; las descubre a través de este registro.
"""

from __future__ import annotations

from typing import Any

# Alias ISO-3166 alpha-3 -> alpha-2 canonicos soportados
_ALIAS_PAIS_ISO: dict[str, str] = {
    "VEN": "VE",
}

# pais_codigo_iso normalizado (mayúsculas, alpha-2) -> {nombre_puerto: instancia/clase}
_LOCALIZACIONES: dict[str, dict[str, Any]] = {}


def normalizar_codigo_pais(pais_codigo_iso: str | None) -> str | None:
    """Normaliza código ISO-3166 (p. ej. ``'VE'`` y ``'VEN'`` -> ``'VE'``)."""
    if not pais_codigo_iso:
        return None
    limpio = str(pais_codigo_iso).strip().upper()
    if not limpio:
        return None
    return _ALIAS_PAIS_ISO.get(limpio, limpio)


def register(pais_codigo_iso: str, puertos: dict[str, Any]) -> None:
    """Registra (o reemplaza) la localización de un país usando su código normalizado."""
    normalizado = normalizar_codigo_pais(pais_codigo_iso)
    if not normalizado:
        raise ValueError("El código ISO del país no puede estar vacío.")
    _LOCALIZACIONES[normalizado] = dict(puertos)


def get(pais_codigo_iso: str | None) -> dict[str, Any] | None:
    normalizado = normalizar_codigo_pais(pais_codigo_iso)
    if not normalizado:
        return None
    return _LOCALIZACIONES.get(normalizado)


def paises_registrados() -> list[str]:
    return sorted(_LOCALIZACIONES.keys())


def _registrar_localizaciones_bundled() -> None:
    """
    Registra las localizaciones incluidas con el producto (GAP-2 / PR-25).

    Venezuela: registra los 6 puertos de ADR-007 en ``apps.localizacion_ve.adapters``.
    Los adaptadores importan ``fiscal``/``nomina``/``finanzas`` de forma perezosa,
    por lo que instanciarlos durante el arranque es seguro.
    """
    try:
        from apps.localizacion_ve.adapters import (
            CalculadoraNominaVE,
            GeneradorDocumentoLegalVE,
            LibroLegalVE,
            MetodosPagoLocalesVE,
            MotorImpuestosVE,
            ProveedorTasasVE,
        )

        register(
            "VE",
            {
                "MotorImpuestos": MotorImpuestosVE(),
                "GeneradorDocumentoLegal": GeneradorDocumentoLegalVE(),
                "CalculadoraNomina": CalculadoraNominaVE(),
                "LibroLegal": LibroLegalVE(),
                "ProveedorTasas": ProveedorTasasVE(),
                "MetodosPagoLocales": MetodosPagoLocalesVE(),
            },
        )
    except Exception:  # noqa: BLE001 — no romper el arranque si VE no está disponible
        pass


_registrar_localizaciones_bundled()
