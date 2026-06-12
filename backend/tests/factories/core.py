"""Factories de modelos núcleo: Empresa, Moneda, Usuarios."""

import factory
from factory.django import DjangoModelFactory

from django.contrib.auth import get_user_model

from apps.core.models import Empresa
from apps.finanzas.models import Moneda


class MonedaFactory(DjangoModelFactory):
    """Moneda genérica (global, sin empresa). ``codigo_iso`` único por secuencia.

    ``django_get_or_create`` sobre ``codigo_iso`` (heredado de la factory histórica
    de ``tests_api/``): pedir dos veces el mismo código (p. ej. "USD") reutiliza la
    fila en vez de violar el unique.
    """

    class Meta:
        model = Moneda
        django_get_or_create = ("codigo_iso",)

    nombre = factory.Sequence(lambda n: f"Moneda {n}")
    # codigo_iso tiene max_length=5 y es unique; la secuencia genera M0001…M9999.
    codigo_iso = factory.Sequence(lambda n: f"M{n:04d}")
    simbolo = "$"
    tipo_moneda = "fiat"
    decimales = 2
    es_generica = True


class EmpresaFactory(DjangoModelFactory):
    """Empresa (entidad raíz multi-tenant). Crea su moneda base si no se pasa una."""

    class Meta:
        model = Empresa

    nombre_legal = factory.Sequence(lambda n: f"Empresa Test {n} S.A.")
    identificador_fiscal = factory.Sequence(lambda n: f"J-{n:08d}-0")
    id_moneda_base = factory.SubFactory(MonedaFactory)


class UsuariosFactory(DjangoModelFactory):
    """
    Usuario del ERP. Pasa ``empresa=...`` (o una lista en ``empresas=[...]``) para
    asociarlo a uno o más tenants vía el M2M ``empresas``.
    """

    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user_test_{n}")
    email = factory.Sequence(lambda n: f"user_test_{n}@example.com")
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "testpass123")
        if create:
            obj.save(update_fields=["password"])

    @factory.post_generation
    def empresa(obj, create, extracted, **kwargs):
        """Atajo: ``UsuariosFactory(empresa=empresa_a)`` agrega esa única empresa."""
        if create and extracted is not None:
            obj.empresas.add(extracted)

    @factory.post_generation
    def empresas(obj, create, extracted, **kwargs):
        """``UsuariosFactory(empresas=[empresa_a, empresa_b])`` agrega varias."""
        if create and extracted:
            for empresa in extracted:
                obj.empresas.add(empresa)
