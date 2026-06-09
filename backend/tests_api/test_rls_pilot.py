"""Tests de Row Level Security (P0-1 del plan de hardening).

Prueban el aislamiento multi-tenant **a nivel de PostgreSQL**: se consulta el
ORM SIN filtro por empresa (``Sucursal.objects.all()``) y aun así la base de
datos solo devuelve las filas de la empresa fijada en el contexto RLS. Es la
condición de cierre del DoD de P0-1: "fuga cross-tenant verde con el filtro de
aplicación deshabilitado".
"""

import pytest

from apps.core import rls
from apps.core.models import Sucursal

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


@pytest.fixture(autouse=True)
def _enforce_rls_role(rls_test_role):
    """Si el rol de conexión salta RLS (CI superusuario), corre el test con
    ``SET ROLE`` a un rol no-privilegiado para que las políticas RLS se apliquen.
    No-op cuando el rol ya está sujeto a RLS (dev local)."""
    if rls_test_role is None:
        yield
        return
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(f'SET ROLE "{rls_test_role}"')
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")


@pytest.fixture
def sucursales(empresa_a, empresa_b):
    """Crea una sucursal por empresa con el contexto de sistema (bypass on)."""
    rls.apply_system_default()
    a = Sucursal.objects.create(id_empresa=empresa_a, nombre="Sede A", codigo_sucursal="A001")
    b = Sucursal.objects.create(id_empresa=empresa_b, nombre="Sede B", codigo_sucursal="B001")
    yield {"a": a, "b": b}
    # Evita que el contexto fijado en cada test se filtre al siguiente.
    rls.apply_system_default()


def _ids(qs):
    return set(qs.values_list("id_sucursal", flat=True))


def test_rls_aisla_por_empresa_sin_filtro_de_aplicacion(sucursales, empresa_a, empresa_b):
    # Contexto = solo empresa A. El ORM no aplica filtro por empresa aquí.
    rls.apply_context([empresa_a.id_empresa], bypass=False)
    assert _ids(Sucursal.objects.all()) == {sucursales["a"].id_sucursal}

    # Contexto = solo empresa B.
    rls.apply_context([empresa_b.id_empresa], bypass=False)
    assert _ids(Sucursal.objects.all()) == {sucursales["b"].id_sucursal}


def test_rls_bypass_ve_todas(sucursales):
    rls.apply_context([], bypass=True)
    assert _ids(Sucursal.objects.all()) == {
        sucursales["a"].id_sucursal,
        sucursales["b"].id_sucursal,
    }


def test_rls_sin_contexto_es_fail_closed(sucursales):
    # bypass off y sin empresas => no se ve ninguna fila.
    rls.apply_context([], bypass=False)
    assert _ids(Sucursal.objects.all()) == set()


def test_rls_no_permite_insertar_en_otra_empresa(sucursales, empresa_a, empresa_b):
    # Contexto restringido a empresa A: insertar para B debe violar WITH CHECK.
    from django.db import IntegrityError, transaction
    from django.db.utils import ProgrammingError

    rls.apply_context([empresa_a.id_empresa], bypass=False)
    with pytest.raises((IntegrityError, ProgrammingError)):
        with transaction.atomic():
            Sucursal.objects.create(
                id_empresa=empresa_b, nombre="Intrusa", codigo_sucursal="X999"
            )


def test_rls_bypass_context_manager(sucursales):
    rls.apply_context([], bypass=False)
    assert Sucursal.objects.count() == 0
    with rls.rls_bypass():
        assert Sucursal.objects.count() == 2
    # Al salir vuelve al default de sistema (bypass on).
    assert Sucursal.objects.count() == 2


# --- SQL builders -----------------------------------------------------------


def test_build_enable_sql_estructura():
    sql = rls.build_enable_rls_sql("ventas_pedido", "id_empresa_id")
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert f"CREATE POLICY {rls.POLICY_NAME}" in sql
    assert '"id_empresa_id"' in sql


def test_build_disable_sql_estructura():
    sql = rls.build_disable_rls_sql("ventas_pedido")
    assert f"DROP POLICY IF EXISTS {rls.POLICY_NAME}" in sql
    assert "NO FORCE ROW LEVEL SECURITY" in sql
    assert "DISABLE ROW LEVEL SECURITY" in sql


@pytest.mark.parametrize("bad", ["tabla; DROP", "Tabla", "1tabla", "espacio mal"])
def test_build_sql_rechaza_identificadores_invalidos(bad):
    with pytest.raises(ValueError):
        rls.build_enable_rls_sql(bad)
