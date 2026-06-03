"""Valida que las factories del harness (Fase 0) construyen objetos válidos."""
import pytest

from tests_api.factories import (
    AlmacenFactory,
    ClienteFactory,
    EmpresaFactory,
    MonedaFactory,
    ProductoFactory,
    UnidadMedidaFactory,
    UsuarioFactory,
)

pytestmark = pytest.mark.django_db


def test_empresa_factory():
    e = EmpresaFactory()
    assert e.pk and e.id_moneda_base is not None


def test_moneda_factory_unica():
    assert MonedaFactory().codigo_iso != MonedaFactory().codigo_iso


def test_usuario_factory_con_empresa():
    e = EmpresaFactory()
    u = UsuarioFactory(empresas=[e])
    assert u.check_password("testpass123")
    assert e in u.empresas.all()


def test_producto_factory_tenant_consistente():
    p = ProductoFactory()
    # producto, su unidad y su categoría comparten empresa.
    assert p.id_unidad_medida_base.id_empresa_id == p.id_empresa_id
    assert p.id_categoria.id_empresa_id == p.id_empresa_id


def test_producto_en_empresa_dada():
    e = EmpresaFactory()
    p = ProductoFactory(id_empresa=e)
    assert p.id_empresa_id == e.pk


def test_almacen_y_unidad_y_cliente():
    e = EmpresaFactory()
    assert AlmacenFactory(id_empresa=e).id_empresa_id == e.pk
    assert UnidadMedidaFactory(id_empresa=e).id_empresa_id == e.pk
    assert ClienteFactory(id_empresa=e).id_empresa_id == e.pk
