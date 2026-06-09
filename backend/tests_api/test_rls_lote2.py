"""Tests de Row Level Security — lote 2 (P0-1 rollout): inventario / compras / crm.

Verifican el aislamiento multi-tenant **a nivel de PostgreSQL** sobre las tablas
incorporadas en el segundo lote de RLS. Como en ``test_rls_pilot.py``, se consulta
el ORM SIN filtro por empresa y aun así la base de datos solo devuelve las filas de
la empresa fijada en el contexto RLS (DoD de P0-1: "fuga cross-tenant verde con el
filtro de aplicación deshabilitado").

Se cubren dos de las tablas nuevas (``crm_cliente`` y ``crm_contacto_cliente``),
ambas con la columna por defecto ``id_empresa_id``.
"""

import pytest

from apps.core import rls
from apps.crm.models import Cliente, ContactoCliente

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


@pytest.fixture(autouse=True)
def _enforce_rls_role(rls_test_role):
    """Corre el test bajo un rol sujeto a RLS si el rol de conexión la salta
    (CI superusuario); no-op en dev local. Ver tests_api/conftest.py."""
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
def clientes(empresa_a, empresa_b):
    """Crea un cliente por empresa con el contexto de sistema (bypass on)."""
    rls.apply_system_default()
    a = Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente Alpha", rif="J-11111111-1"
    )
    b = Cliente.objects.create(
        id_empresa=empresa_b, razon_social="Cliente Beta", rif="J-22222222-2"
    )
    yield {"a": a, "b": b}
    # Evita que el contexto fijado en cada test se filtre al siguiente.
    rls.apply_system_default()


@pytest.fixture
def contactos(clientes, empresa_a, empresa_b):
    """Un contacto por empresa, ligado a su cliente (bypass on)."""
    rls.apply_system_default()
    a = ContactoCliente.objects.create(
        id_empresa=empresa_a,
        id_cliente=clientes["a"],
        nombre_contacto="Ana",
        apellido_contacto="Alpha",
        email_contacto="ana@alpha.test",
    )
    b = ContactoCliente.objects.create(
        id_empresa=empresa_b,
        id_cliente=clientes["b"],
        nombre_contacto="Beto",
        apellido_contacto="Beta",
        email_contacto="beto@beta.test",
    )
    yield {"a": a, "b": b}
    rls.apply_system_default()


def _cliente_ids(qs):
    return set(qs.values_list("id_cliente", flat=True))


def _contacto_ids(qs):
    return set(qs.values_list("id_contacto", flat=True))


# --- crm_cliente ------------------------------------------------------------


def test_cliente_rls_aisla_por_empresa_sin_filtro_de_aplicacion(
    clientes, empresa_a, empresa_b
):
    # Contexto = solo empresa A. El ORM no aplica filtro por empresa aquí.
    rls.apply_context([empresa_a.id_empresa], bypass=False)
    assert _cliente_ids(Cliente.objects.all()) == {clientes["a"].id_cliente}

    # Contexto = solo empresa B.
    rls.apply_context([empresa_b.id_empresa], bypass=False)
    assert _cliente_ids(Cliente.objects.all()) == {clientes["b"].id_cliente}


def test_cliente_rls_sin_contexto_es_fail_closed(clientes):
    rls.apply_context([], bypass=False)
    assert _cliente_ids(Cliente.objects.all()) == set()


def test_cliente_rls_bypass_ve_todas(clientes):
    rls.apply_context([], bypass=True)
    assert _cliente_ids(Cliente.objects.all()) == {
        clientes["a"].id_cliente,
        clientes["b"].id_cliente,
    }


def test_cliente_rls_no_permite_insertar_en_otra_empresa(clientes, empresa_a, empresa_b):
    from django.db import IntegrityError, transaction
    from django.db.utils import ProgrammingError

    rls.apply_context([empresa_a.id_empresa], bypass=False)
    with pytest.raises((IntegrityError, ProgrammingError)):
        with transaction.atomic():
            Cliente.objects.create(
                id_empresa=empresa_b, razon_social="Intrusa", rif="J-99999999-9"
            )


# --- crm_contacto_cliente ---------------------------------------------------


def test_contacto_rls_aisla_por_empresa_sin_filtro_de_aplicacion(
    contactos, empresa_a, empresa_b
):
    rls.apply_context([empresa_a.id_empresa], bypass=False)
    assert _contacto_ids(ContactoCliente.objects.all()) == {contactos["a"].id_contacto}

    rls.apply_context([empresa_b.id_empresa], bypass=False)
    assert _contacto_ids(ContactoCliente.objects.all()) == {contactos["b"].id_contacto}


def test_contacto_rls_sin_contexto_es_fail_closed(contactos):
    rls.apply_context([], bypass=False)
    assert _contacto_ids(ContactoCliente.objects.all()) == set()


def test_contacto_rls_bypass_ve_todas(contactos):
    rls.apply_context([], bypass=True)
    assert _contacto_ids(ContactoCliente.objects.all()) == {
        contactos["a"].id_contacto,
        contactos["b"].id_contacto,
    }
