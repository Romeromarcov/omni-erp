"""
Factories ``factory_boy`` tenant-aware para la suite de tests.

Convención (plan cero-dudas §B0): toda factory de un modelo tenant-aware exige
una ``Empresa`` explícita (no se inventa una por defecto silenciosa), para que el
test sea siempre claro sobre a qué tenant pertenece cada objeto.
"""

from tests.factories.comercial import (
    AlmacenFactory,
    CategoriaProductoFactory,
    ClienteFactory,
    ProductoFactory,
    UnidadMedidaFactory,
)
from tests.factories.core import EmpresaFactory, MonedaFactory, UsuariosFactory

__all__ = [
    "AlmacenFactory",
    "CategoriaProductoFactory",
    "ClienteFactory",
    "EmpresaFactory",
    "MonedaFactory",
    "ProductoFactory",
    "UnidadMedidaFactory",
    "UsuariosFactory",
]
