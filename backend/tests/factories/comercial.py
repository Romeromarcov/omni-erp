"""Factories de catálogo comercial: inventario, almacenes y CRM.

Migradas desde ``tests_api/factories.py`` (CTF-014). Las factories núcleo
(``EmpresaFactory``, ``MonedaFactory``, ``UsuariosFactory``) viven en
``tests/factories/core.py``; aquí solo las de modelos tenant-aware de
inventario/almacenes/crm que las componen.

Uso:
    from tests.factories import EmpresaFactory, ProductoFactory
    empresa = EmpresaFactory()
    producto = ProductoFactory(id_empresa=empresa)
"""
from decimal import Decimal

import factory

from tests.factories.core import EmpresaFactory, MonedaFactory


class UnidadMedidaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "inventario.UnidadMedida"

    id_empresa = factory.SubFactory(EmpresaFactory)
    nombre = factory.Sequence(lambda n: f"Unidad {n}")
    abreviatura = factory.Sequence(lambda n: f"U{n}")
    tipo = "CANTIDAD"


class CategoriaProductoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "inventario.CategoriaProducto"

    id_empresa = factory.SubFactory(EmpresaFactory)
    nombre_categoria = factory.Sequence(lambda n: f"Categoría {n}")


class ProductoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "inventario.Producto"

    id_empresa = factory.SubFactory(EmpresaFactory)
    nombre_producto = factory.Sequence(lambda n: f"Producto {n}")
    id_unidad_medida_base = factory.SubFactory(
        UnidadMedidaFactory, id_empresa=factory.SelfAttribute("..id_empresa")
    )
    id_categoria = factory.SubFactory(
        CategoriaProductoFactory, id_empresa=factory.SelfAttribute("..id_empresa")
    )
    id_moneda_precio = factory.SubFactory(MonedaFactory)
    precio_venta_sugerido = Decimal("10.00")
    costo_promedio = Decimal("5.00")


class AlmacenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "almacenes.Almacen"

    id_empresa = factory.SubFactory(EmpresaFactory)
    nombre_almacen = factory.Sequence(lambda n: f"Almacén {n}")
    codigo_almacen = factory.Sequence(lambda n: f"AC-{n}")


class ClienteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "crm.Cliente"

    id_empresa = factory.SubFactory(EmpresaFactory)
    razon_social = factory.Sequence(lambda n: f"Cliente {n} C.A.")
    rif = factory.Sequence(lambda n: f"J-{n:08d}-0")
