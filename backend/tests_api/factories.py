"""Factories tenant-aware (factory_boy) — base del harness de tests (Fase 0).

Centraliza la creación de objetos para los tests, evitando setup repetido y
facilitando los tests de aislamiento y de integración. Todas las factories de
modelos tenant aceptan/crean su `empresa`.

Uso:
    from tests_api.factories import EmpresaFactory, ProductoFactory
    empresa = EmpresaFactory()
    producto = ProductoFactory(id_empresa=empresa)
"""
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model


class MonedaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "finanzas.Moneda"
        django_get_or_create = ("codigo_iso",)

    nombre = factory.Sequence(lambda n: f"Moneda {n}")
    codigo_iso = factory.Sequence(lambda n: f"M{n:02d}")
    simbolo = "$"
    tipo_moneda = "fiat"
    es_generica = True


class EmpresaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "core.Empresa"

    nombre_legal = factory.Sequence(lambda n: f"Empresa Test {n} S.A.")
    identificador_fiscal = factory.Sequence(lambda n: f"J-{n:08d}-9")
    id_moneda_base = factory.SubFactory(MonedaFactory)


class UsuarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.Sequence(lambda n: f"user_{n}@test.local")
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "testpass123")
        if create:
            self.save()

    @factory.post_generation
    def empresas(self, create, extracted, **kwargs):
        if not create:
            return
        for empresa in (extracted or []):
            self.empresas.add(empresa)


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
