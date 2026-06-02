"""
Adaptadores VE de los puertos de localización (ADR-007 / GAP-2, strangler fig).

Inicialmente DELEGAN en la lógica fiscal existente (`apps/fiscal`) en vez de
mover el código de golpe. El import de fiscal es perezoso (dentro del método)
para no romper el orden de carga de apps.
"""
from decimal import Decimal

from apps.localizacion.ports import MotorImpuestos


class MotorImpuestosVE(MotorImpuestos):
    """Motor de impuestos venezolano: IVA + IGTF (delega en apps.fiscal)."""

    def calcular(self, *, subtotal: Decimal, empresa, contexto: dict | None = None) -> dict:
        from apps.fiscal.services import calcular_impuestos

        return calcular_impuestos(Decimal(str(subtotal)), empresa)
