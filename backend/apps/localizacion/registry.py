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


def _registrar_localizaciones_bundled() -> None:
    """
    Registra las localizaciones que vienen con el producto (GAP-2).

    Venezuela: ``MotorImpuestosVE`` delega en apps.fiscal (strangler fig). El
    adaptador importa fiscal de forma perezosa, así que registrar la instancia
    aquí es seguro durante la carga de apps.
    """
    try:
        from apps.localizacion_ve.adapters import MotorImpuestosVE

        register("VE", {"MotorImpuestos": MotorImpuestosVE()})
    except Exception:  # noqa: BLE001 — no romper el arranque si VE no está disponible
        pass


_registrar_localizaciones_bundled()
