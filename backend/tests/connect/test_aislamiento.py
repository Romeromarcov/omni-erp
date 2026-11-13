"""Aislamiento multi-tenant real (RLS) de Omni Connect y el CRM ligero (S1).

Mismo patrón que ``tests/tenant/test_rls_rollout.py``: el ORM consulta SIN filtro
por empresa y es PostgreSQL (política ``omni_rls_tenant``) quien acota las filas.
R-CODE-1: la empresa A nunca ve ni escribe datos de la empresa B.
"""

import pytest

from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError

from apps.core import rls

from .builders import (
    crear_etapa,
    crear_lead,
    crear_perfil,
    crear_pipeline,
    crear_tarjeta,
    crear_toque,
    crear_usuario,
)

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]

TABLAS = [
    "connect_perfil",
    "connect_tarjeta",
    "connect_toque",
    "crm_pipeline",
    "crm_etapa",
    "crm_lead",
]


@pytest.fixture(autouse=True)
def _enforce_rls_role(rls_test_role):
    """Corre bajo un rol sujeto a RLS si el de conexión la salta (CI superusuario)."""
    if rls_test_role is None:
        yield
        return
    with connection.cursor() as cur:
        cur.execute(f'SET ROLE "{rls_test_role}"')
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")


# (tabla, builder(empresa) -> objeto)
_BUILDERS = [
    ("connect_perfil", crear_perfil),
    ("connect_tarjeta", crear_tarjeta),
    ("connect_toque", crear_toque),
    ("crm_pipeline", crear_pipeline),
    ("crm_etapa", crear_etapa),
    ("crm_lead", crear_lead),
]


def test_las_seis_tablas_estan_en_el_registro_rls():
    faltan = [t for t in TABLAS if t not in rls.RLS_TABLES]
    assert not faltan, f"Tablas de Connect/CRM sin registrar en RLS: {faltan}"
    assert all(rls.RLS_TABLES[t] == "id_empresa_id" for t in TABLAS)


@pytest.mark.parametrize("tabla,builder", _BUILDERS, ids=[t for t, _ in _BUILDERS])
def test_aisla_por_empresa_sin_filtro_de_aplicacion(tabla, builder, empresa_a, empresa_b):
    rls.apply_system_default()
    obj_a, obj_b = builder(empresa_a), builder(empresa_b)
    modelo = type(obj_a)
    try:
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        assert set(modelo.objects.values_list("pk", flat=True)) == {obj_a.pk}

        rls.apply_context([empresa_b.id_empresa], bypass=False)
        assert set(modelo.objects.values_list("pk", flat=True)) == {obj_b.pk}

        # Sin contexto => fail-closed; con bypass de sistema => todo visible.
        rls.apply_context([], bypass=False)
        assert modelo.objects.count() == 0
        rls.apply_context([], bypass=True)
        assert set(modelo.objects.values_list("pk", flat=True)) == {obj_a.pk, obj_b.pk}
    finally:
        rls.apply_system_default()


def _preparar_insercion(tabla, empresa):
    """Crea (con bypass) las dependencias de ``empresa`` y devuelve ``insertar()``.

    ``insertar()`` ejecuta UNA sola escritura: la fila final de ``tabla``. Así,
    si falla, es por la política RLS y no porque falló una dependencia previa.
    """
    if tabla == "connect_perfil":
        usuario = crear_usuario(empresa)
        return lambda: crear_perfil(empresa, usuario=usuario)
    if tabla == "connect_tarjeta":
        return lambda: crear_tarjeta(empresa)
    if tabla == "connect_toque":
        perfil = crear_perfil(empresa)
        return lambda: crear_toque(empresa, perfil=perfil)
    if tabla == "crm_pipeline":
        return lambda: crear_pipeline(empresa)
    if tabla == "crm_etapa":
        pipeline = crear_pipeline(empresa)
        return lambda: crear_etapa(empresa, pipeline)
    if tabla == "crm_lead":
        pipeline = crear_pipeline(empresa)
        etapa = crear_etapa(empresa, pipeline)
        usuario = crear_usuario(empresa)
        return lambda: crear_lead(empresa, pipeline, etapa, usuario)
    raise AssertionError(tabla)


@pytest.mark.parametrize("tabla", TABLAS)
def test_no_permite_insertar_en_otra_empresa(tabla, empresa_a, empresa_b):
    rls.apply_system_default()
    insertar_b = _preparar_insercion(tabla, empresa_b)
    try:
        # Control: en el contexto de B la misma escritura es válida.
        rls.apply_context([empresa_b.id_empresa], bypass=False)
        with transaction.atomic():
            insertar_b()

        # Bajo el contexto de A, escribir una fila de B lo rechaza WITH CHECK.
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        with pytest.raises((IntegrityError, ProgrammingError)), transaction.atomic():
            insertar_b()
    finally:
        rls.apply_system_default()


def test_no_se_puede_mover_un_lead_a_otra_empresa(empresa_a, empresa_b):
    """UPDATE que cambia id_empresa a un tenant no visible también lo bloquea WITH CHECK."""
    rls.apply_system_default()
    lead = crear_lead(empresa_a)
    try:
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        with pytest.raises((IntegrityError, ProgrammingError)), transaction.atomic():
            type(lead).objects.filter(pk=lead.pk).update(id_empresa=empresa_b)
    finally:
        rls.apply_system_default()
