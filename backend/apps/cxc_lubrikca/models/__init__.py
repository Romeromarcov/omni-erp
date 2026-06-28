"""Modelos del subproyecto CxC Lubrikca.

Fase 1: modelos de configuración del motor con *effective dating* sobre la base
abstracta ``CxcLubrikcaBaseModel`` (UUIDv7 + multi-tenant + timestamps + soft
delete). Fases siguientes: espejo de Odoo, bandeja de facturación, equivalentes.
"""

from .base import CxcLubrikcaBaseModel
from .config import (
    Condicion,
    DescuentoBCVCompleto,
    DescuentoMarcaCategoria,
    Feriado,
    MetodoPago,
    Moneda,
    PromocionPrimeraCompra,
    ReglaRecurrencia,
    TipoBeneficio,
    TipoDescuento,
    TipoFeriado,
    TipoTasa,
)
from .operacion import (
    BandejaFacturacion,
    EstadoBandeja,
    EstadoEntrega,
    EstadoVinculacion,
    LineaPedidoLubrikca,
    PagoLubrikca,
    PedidoLubrikca,
    PrecioListaLubrikca,
    Vinculacion,
)

__all__ = [
    "CxcLubrikcaBaseModel",
    "Condicion",
    "DescuentoBCVCompleto",
    "DescuentoMarcaCategoria",
    "Feriado",
    "MetodoPago",
    "Moneda",
    "PromocionPrimeraCompra",
    "ReglaRecurrencia",
    "TipoBeneficio",
    "TipoDescuento",
    "TipoFeriado",
    "TipoTasa",
    # Operación (Fase 3)
    "BandejaFacturacion",
    "EstadoBandeja",
    "EstadoEntrega",
    "EstadoVinculacion",
    "LineaPedidoLubrikca",
    "PagoLubrikca",
    "PedidoLubrikca",
    "PrecioListaLubrikca",
    "Vinculacion",
]
