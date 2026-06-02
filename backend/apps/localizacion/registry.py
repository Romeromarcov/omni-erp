"""
Registro de localizaciones (ADR-007).

Cada localización se registra por código ISO de país con las implementaciones
de los puertos que provee. El núcleo nunca importa las localizaciones
directamente; las descubre a través de este registro.
"""

# pais_codigo_iso (mayúsculas) → {nombre_puerto: instancia/clase}
_LOCALIZACIONES: dict[str, dict] = {}


def register(pais_codigo_iso: str, puertos: dict) -> None:
    """Registra (o reemplaza) la localización de un país."""
    _LOCALIZACIONES[pais_codigo_iso.upper()] = dict(puertos)


def get(pais_codigo_iso: str | None) -> dict | None:
    if not pais_codigo_iso:
        return None
    return _LOCALIZACIONES.get(pais_codigo_iso.upper())


def paises_registrados() -> list[str]:
    return sorted(_LOCALIZACIONES.keys())
