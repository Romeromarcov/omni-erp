"""Crea/actualiza el rol de aplicación no-dueño para RLS (CTF-012).

PostgreSQL no aplica RLS al rol *dueño* de una tabla salvo ``FORCE ROW LEVEL
SECURITY``, y un rol con ``SUPERUSER``/``BYPASSRLS`` la salta siempre. El
modelo robusto (fail-closed por construcción) es que el **runtime** conecte
con un rol dedicado, no-dueño y sin esos atributos, mientras las migraciones
siguen corriendo con el rol dueño actual.

Este comando es **idempotente** y debe correrse conectado como el rol dueño
(el de migraciones), p. ej. tras cada ``migrate`` o al preparar un entorno:

    OMNI_APP_DB_PASSWORD=... python manage.py configurar_rol_rls

- La contraseña se toma SOLO de la variable de entorno ``OMNI_APP_DB_PASSWORD``
  (nunca por argumento: quedaría en el historial de shell / lista de procesos)
  y jamás se imprime (R-CODE-8). Si el rol ya existe puede omitirse: se
  reaplican atributos y GRANTs sin tocar la contraseña.
- GRANTs mínimos de runtime: ``CONNECT`` a la BD, ``USAGE`` del esquema,
  ``SELECT/INSERT/UPDATE/DELETE`` sobre las tablas y ``USAGE/SELECT/UPDATE``
  sobre las secuencias. Sin DDL: el rol no puede crear ni alterar objetos.
- ``ALTER DEFAULT PRIVILEGES`` deja cubiertas las tablas/secuencias que el rol
  dueño cree en migraciones futuras (re-correr el comando también las cubre).

El runbook de activación (cambiar ``DATABASE_URL`` del runtime en Railway) es
``docs/runbooks/RUNBOOK_RLS_ROL_APP.md``.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg2 import sql

from apps.core.rls import _check_ident

ENV_PASSWORD = "OMNI_APP_DB_PASSWORD"
ENV_ROL = "OMNI_APP_DB_ROLE"
DEFAULT_ROL = "omni_app"

# Atributos del rol: login sí; nada de privilegios que salten RLS o hagan DDL.
_ATRIBUTOS = (
    "LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT"
)


class Command(BaseCommand):
    help = (
        "Crea/actualiza el rol de aplicación no-dueño (NOSUPERUSER NOBYPASSRLS) "
        "con GRANTs mínimos para que RLS aplique al runtime (CTF-012). "
        f"Contraseña vía ${ENV_PASSWORD} (nunca se imprime)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--rol",
            default=os.environ.get(ENV_ROL, DEFAULT_ROL),
            help=f"Nombre del rol de aplicación (default: ${ENV_ROL} o '{DEFAULT_ROL}').",
        )

    def handle(self, *args, **options):
        rol = options["rol"]
        try:
            _check_ident(rol)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        password = os.environ.get(ENV_PASSWORD) or None

        with connection.cursor() as cursor:
            raw = cursor.cursor  # cursor psycopg2 real, para componer SQL seguro
            ident = sql.Identifier(rol)

            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [rol])
            existe = cursor.fetchone() is not None

            if not existe and password is None:
                raise CommandError(
                    f"El rol '{rol}' no existe y falta la variable de entorno "
                    f"{ENV_PASSWORD} para crearlo con contraseña."
                )

            if existe:
                # Reasegura atributos (p. ej. si alguien le dio BYPASSRLS a mano).
                stmt = sql.SQL("ALTER ROLE {} WITH " + _ATRIBUTOS).format(ident)
                if password is not None:
                    stmt = sql.SQL("ALTER ROLE {} WITH " + _ATRIBUTOS + " PASSWORD {}").format(
                        ident, sql.Literal(password)
                    )
                cursor.execute(stmt.as_string(raw))
                accion = "actualizado"
            else:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} WITH " + _ATRIBUTOS + " PASSWORD {}")
                    .format(ident, sql.Literal(password))
                    .as_string(raw)
                )
                accion = "creado"

            cursor.execute("SELECT current_database()")
            db_name = cursor.fetchone()[0]

            grants = [
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(db_name), ident
                ),
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(ident),
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON ALL TABLES IN SCHEMA public TO {}"
                ).format(ident),
                sql.SQL(
                    "GRANT USAGE, SELECT, UPDATE "
                    "ON ALL SEQUENCES IN SCHEMA public TO {}"
                ).format(ident),
                # Tablas/secuencias futuras creadas por el rol dueño (migraciones).
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(ident),
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
                ).format(ident),
            ]
            for stmt in grants:
                cursor.execute(stmt.as_string(raw))

        self.stdout.write(
            self.style.SUCCESS(
                f"Rol '{rol}' {accion}: LOGIN, sin SUPERUSER/BYPASSRLS/DDL; "
                f"GRANTs CRUD + secuencias en '{db_name}' (incl. default privileges). "
                f"Siguiente paso: runbook docs/runbooks/RUNBOOK_RLS_ROL_APP.md."
            )
        )
