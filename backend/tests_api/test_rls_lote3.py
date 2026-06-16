"""Tests de Row Level Security — lote 3 (P0-1 rollout): despacho (1.G).

Mismo contrato que ``test_rls_pilot.py`` / ``test_rls_lote2.py``: se consulta el
ORM SIN filtro por empresa y aun así PostgreSQL solo devuelve las filas de la
empresa fijada en el contexto RLS (defensa en profundidad bajo R-CODE-1).

Cubre ``despacho_despacho`` (columna por defecto ``id_empresa_id``), registrada
en ``apps/core/rls.py`` y activada por la migración ``0003_rls_lote3_despacho``.
"""

import pytest
from django.utils import timezone

from apps.core import rls
from apps.despacho.models import Despacho

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


def _despacho(empresa, numero):
    from apps.almacenes.models import Almacen

    almacen = Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen=f"Almacén RLS {numero}",
        codigo_almacen=f"ALM-RLS-{numero}",
    )
    return Despacho.objects.create(
        id_empresa=empresa,
        numero_despacho=numero,
        fecha_despacho=timezone.now(),
        id_almacen_origen=almacen,
        direccion_destino="Destino RLS",
    )


@pytest.fixture
def despachos(empresa_a, empresa_b):
    """Un despacho por empresa, creados con contexto de sistema (bypass on)."""
    rls.apply_system_default()
    a = _despacho(empresa_a, "DSP-RLS-A")
    b = _despacho(empresa_b, "DSP-RLS-B")
    yield {"a": a, "b": b}
    # Evita que el contexto fijado en cada test se filtre al siguiente.
    rls.apply_system_default()


def _ids(qs):
    return set(qs.values_list("id_despacho", flat=True))


def test_despacho_rls_aisla_por_empresa_sin_filtro_de_aplicacion(
    despachos, empresa_a, empresa_b
):
    # Contexto = solo empresa A. El ORM no aplica filtro por empresa aquí.
    rls.apply_context([empresa_a.id_empresa], bypass=False)
    assert _ids(Despacho.objects.all()) == {despachos["a"].id_despacho}

    # Contexto = solo empresa B.
    rls.apply_context([empresa_b.id_empresa], bypass=False)
    assert _ids(Despacho.objects.all()) == {despachos["b"].id_despacho}


def test_despacho_rls_sin_contexto_es_fail_closed(despachos):
    rls.apply_context([], bypass=False)
    assert _ids(Despacho.objects.all()) == set()


def test_despacho_rls_bypass_ve_todas(despachos):
    rls.apply_context([], bypass=True)
    assert _ids(Despacho.objects.all()) == {
        despachos["a"].id_despacho,
        despachos["b"].id_despacho,
    }


def test_despacho_rls_no_permite_insertar_en_otra_empresa(
    despachos, empresa_a, empresa_b
):
    from django.db import IntegrityError, transaction
    from django.db.utils import ProgrammingError

    rls.apply_context([empresa_a.id_empresa], bypass=False)
    with pytest.raises((IntegrityError, ProgrammingError)):
        with transaction.atomic():
            Despacho.objects.create(
                id_empresa=empresa_b,
                numero_despacho="DSP-RLS-INTRUSO",
                fecha_despacho=timezone.now(),
                id_almacen_origen=despachos["b"].id_almacen_origen,
                direccion_destino="Intrusión",
            )
