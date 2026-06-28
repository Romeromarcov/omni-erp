"""Price resolver respaldado por la BD (Fase 3).

Implementa el contrato ``motor.price_resolver.PriceResolver`` leyendo
``PrecioListaLubrikca`` de un tenant. Mantiene el contrato de
``DictPriceResolver``: ``KeyError`` cuando no existe el precio.

En Fase 5 ``PrecioListaLubrikca`` se sincroniza desde Odoo; el motor lo lee
siempre vía este resolver (nunca el "35%" — sección 4.2).
"""

from __future__ import annotations

from decimal import Decimal

from apps.cxc_lubrikca.models import PrecioListaLubrikca
from apps.cxc_lubrikca.services.motor.price_resolver import PriceResolver


class DBPriceResolver(PriceResolver):
    """Resolver que consulta ``PrecioListaLubrikca`` por empresa.

    Carga todos los precios vigentes (no soft-deleted) de la empresa una sola
    vez en un dict en memoria, para evitar N+1 cuando el motor recorre líneas.
    """

    def __init__(self, empresa, *, precios: dict[tuple[str, str], Decimal] | None = None) -> None:
        self._empresa = empresa
        if precios is not None:
            self._precios = dict(precios)
        else:
            self._precios = {
                (row.producto, row.lista): row.precio
                for row in PrecioListaLubrikca.objects.filter(
                    empresa=empresa, deleted_at__isnull=True
                )
            }

    def precio(self, producto: str, lista: str) -> Decimal:
        try:
            return self._precios[(producto, lista)]
        except KeyError as exc:
            raise KeyError(
                f"Sin precio para producto={producto!r} en lista={lista!r}"
            ) from exc
