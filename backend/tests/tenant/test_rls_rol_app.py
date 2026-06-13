"""Tests del comando ``configurar_rol_rls`` (CTF-012).

Verifican que el rol de aplicación no-dueño se crea idempotentemente con los
atributos correctos (``LOGIN``, sin ``SUPERUSER``/``BYPASSRLS``) y los GRANTs
mínimos de runtime, sin imprimir jamás la contraseña (R-CODE-8).

Crear roles requiere ``CREATEROLE``/superusuario en la conexión (el caso de CI
y del rol dueño en Railway); si el rol de conexión no puede, se omiten.
``CREATE ROLE`` es transaccional en PostgreSQL, así que el rollback por test
de ``django_db`` no deja roles huérfanos.
"""

import io

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.core.management.commands.configurar_rol_rls import ENV_PASSWORD

pytestmark = pytest.mark.django_db

ROL = "omni_app_test_ctf012"
PASSWORD = "solo-para-tests-ctf012"  # nosec B105 — credencial efímera de test


@pytest.fixture
def rol_limpio(db):
    """Skip si la conexión no puede crear roles; garantiza que ROL no exista."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
        )
        if not cur.fetchone()[0]:
            pytest.skip("El rol de conexión no tiene CREATEROLE; no se puede probar")

    def _drop():
        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [ROL])
            if cur.fetchone():
                cur.execute(f'DROP OWNED BY "{ROL}"')
                cur.execute(f'DROP ROLE "{ROL}"')

    _drop()
    yield ROL
    _drop()


def _atributos_rol():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole"
            " FROM pg_roles WHERE rolname = %s",
            [ROL],
        )
        return cur.fetchone()


def test_crea_rol_no_dueno_con_grants_minimos(rol_limpio, monkeypatch):
    monkeypatch.setenv(ENV_PASSWORD, PASSWORD)
    salida = io.StringIO()
    call_command("configurar_rol_rls", rol=ROL, stdout=salida)

    atributos = _atributos_rol()
    assert atributos is not None, "El rol no fue creado"
    canlogin, super_, bypassrls, createdb, createrole = atributos
    assert canlogin, "El rol debe poder hacer LOGIN"
    assert not super_, "El rol NO debe ser SUPERUSER (saltaría RLS)"
    assert not bypassrls, "El rol NO debe tener BYPASSRLS (saltaría RLS)"
    assert not createdb and not createrole, "El rol no debe poder hacer DDL de cluster"

    with connection.cursor() as cur:
        # CRUD sobre una tabla con RLS y USAGE del esquema.
        for privilegio in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            cur.execute(
                "SELECT has_table_privilege(%s, 'public.sucursales', %s)",
                [ROL, privilegio],
            )
            assert cur.fetchone()[0], f"Falta GRANT {privilegio} sobre sucursales"
        cur.execute("SELECT has_schema_privilege(%s, 'public', 'USAGE')", [ROL])
        assert cur.fetchone()[0], "Falta USAGE sobre el esquema public"
        # Secuencias (si el esquema tiene; las PK UUID no generan secuencias).
        cur.execute(
            "SELECT c.oid::regclass::text FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE c.relkind = 'S' AND n.nspname = 'public' LIMIT 1"
        )
        secuencia = cur.fetchone()
        if secuencia:
            cur.execute(
                "SELECT has_sequence_privilege(%s, %s, 'USAGE')", [ROL, secuencia[0]]
            )
            assert cur.fetchone()[0], f"Falta USAGE sobre la secuencia {secuencia[0]}"
        # Default privileges para tablas futuras del rol dueño.
        cur.execute(
            "SELECT count(*) FROM pg_default_acl d"
            " WHERE d.defaclacl::text LIKE %s",
            [f"%{ROL}=%"],
        )
        assert cur.fetchone()[0] >= 1, "Faltan ALTER DEFAULT PRIVILEGES hacia el rol"

    # R-CODE-8: la contraseña jamás aparece en la salida.
    assert PASSWORD not in salida.getvalue()
    assert ROL in salida.getvalue()


def test_es_idempotente_y_no_requiere_password_si_ya_existe(rol_limpio, monkeypatch):
    monkeypatch.setenv(ENV_PASSWORD, PASSWORD)
    call_command("configurar_rol_rls", rol=ROL, stdout=io.StringIO())

    # Segunda corrida sin contraseña: reaplica atributos/GRANTs sin fallar.
    monkeypatch.delenv(ENV_PASSWORD, raising=False)
    salida = io.StringIO()
    call_command("configurar_rol_rls", rol=ROL, stdout=salida)
    assert "actualizado" in salida.getvalue()
    assert not _atributos_rol()[1]  # sigue sin SUPERUSER


def test_reaplica_atributos_si_alguien_dio_bypassrls(rol_limpio, monkeypatch):
    monkeypatch.setenv(ENV_PASSWORD, PASSWORD)
    call_command("configurar_rol_rls", rol=ROL, stdout=io.StringIO())
    with connection.cursor() as cur:
        cur.execute(f'ALTER ROLE "{ROL}" WITH BYPASSRLS')
    assert _atributos_rol()[2]  # quedó inseguro a propósito

    call_command("configurar_rol_rls", rol=ROL, stdout=io.StringIO())
    assert not _atributos_rol()[2], "El comando debe quitar BYPASSRLS al reaplicar"


def test_falla_sin_password_si_el_rol_no_existe(rol_limpio, monkeypatch):
    monkeypatch.delenv(ENV_PASSWORD, raising=False)
    with pytest.raises(CommandError, match=ENV_PASSWORD):
        call_command("configurar_rol_rls", rol=ROL, stdout=io.StringIO())


def test_rechaza_nombre_de_rol_invalido(db, monkeypatch):
    monkeypatch.setenv(ENV_PASSWORD, PASSWORD)
    with pytest.raises(CommandError, match="Identificador SQL inválido"):
        call_command("configurar_rol_rls", rol='mal"; DROP ROLE x;--', stdout=io.StringIO())
