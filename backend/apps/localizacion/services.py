"""
Resolución de localización por empresa (ADR-007).

``get_localizacion(empresa)`` devuelve el conjunto de puertos aplicables según
el país de la empresa y sus flags de capa. Si una capa está desactivada, los
puertos de esa capa se reemplazan por no-ops.
"""
from . import ports, registry


def get_localizacion(empresa) -> dict:
    """
    Devuelve {nombre_puerto: implementación} para la empresa.

    - Si la empresa no tiene país registrado: solo no-ops (núcleo agnóstico).
    - Si ``localizacion_legal_activa`` es False: los puertos legales son no-op.
    - (La capa de mercado se gobierna análogamente con ``localizacion_mercado_activa``.)
    """
    pais = getattr(empresa, "pais_codigo_iso", None)
    base = dict(registry.get(pais) or {})

    legal_activa = getattr(empresa, "localizacion_legal_activa", True)
    if not legal_activa:
        base["MotorImpuestos"] = ports.MotorImpuestosNoOp()
        # Otros puertos legales (documento, nómina, libro) caen a None/no-op
        for puerto_legal in ("GeneradorDocumentoLegal", "CalculadoraNomina", "LibroLegal"):
            base.pop(puerto_legal, None)

    if not getattr(empresa, "localizacion_mercado_activa", True):
        for puerto_mercado in ("ProveedorTasas", "MetodosPagoLocales"):
            base.pop(puerto_mercado, None)

    base.setdefault("MotorImpuestos", ports.MotorImpuestosNoOp())
    return base
