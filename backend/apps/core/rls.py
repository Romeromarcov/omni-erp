"""Row Level Security (RLS) — P0-1 del plan de hardening de seguridad.

Ver ``docs/planes/05-seguridad-hardening.md`` (P0-1).

Capa de aislamiento multi-tenant **a nivel de PostgreSQL**, como defensa en
profundidad sobre el filtrado a nivel de aplicación (``get_empresas_visible``).
Si un queryset olvidara el filtro por empresa, la base de datos sigue evitando
la fuga cross-tenant.

Modelo de enforcement
---------------------
- GUC ``omni.rls_empresas``: lista CSV de UUIDs de empresas visibles.
- GUC ``omni.rls_bypass``: ``'on'`` => la fila siempre es visible (superusuario
  Omni y contextos de sistema). Cualquier otro valor / ausente => ``'off'``.
- Política por tabla: la fila es visible si ``bypass='on'`` **o** su columna de
  empresa pertenece al conjunto de ``omni.rls_empresas``. Sin contexto fijado la
  expresión evalúa a falso => **0 filas (fail-closed)**.
- ``FORCE ROW LEVEL SECURITY``: necesario porque la aplicación se conecta con el
  rol *dueño* de las tablas; sin ``FORCE`` el dueño saltaría las políticas.

Estado por defecto de las conexiones
------------------------------------
El signal ``connection_created`` (``apps/core/signals.py``) fija ``bypass='on'``
en **toda** conexión Django nueva. Así las migraciones, Celery, el shell y los
tests operan con acceso total y no se rompen al activar ``FORCE``. El middleware
web (``apps/core/middleware.py``) baja ``bypass`` a ``'off'`` y fija el conjunto
de empresas **solo** para requests HTTP autenticados, que son la superficie
expuesta. Una conexión externa directa (``psql`` con el rol de la app) que no
fije los GUC queda **fail-closed** (no ve filas), lo que es una defensa extra.

El flag ``settings.RLS_ENABLED`` gobierna únicamente si el middleware aplica el
enforcement; el signal de default y las políticas existen siempre para que la
base de datos nunca quede en un estado inconsistente.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

from django.db import DEFAULT_DB_ALIAS, connections

# Nombres de los parámetros de sesión (GUC) de PostgreSQL.
GUC_EMPRESAS = "omni.rls_empresas"
GUC_BYPASS = "omni.rls_bypass"

# Nombre uniforme de la política en todas las tablas.
POLICY_NAME = "omni_rls_tenant"

# Identificadores SQL permitidos (tabla / columna). Se validan con whitelist
# porque se interpolan en DDL; nunca provienen de entrada de usuario.
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _check_ident(ident: str) -> str:
    if not _IDENT_RE.match(ident):
        raise ValueError(f"Identificador SQL inválido para RLS: {ident!r}")
    return ident


def _predicate(empresa_column: str) -> str:
    col = _check_ident(empresa_column)
    return (
        f"coalesce(current_setting('{GUC_BYPASS}', true), 'off') = 'on' "
        f'OR "{col}"::text = ANY (string_to_array('
        f"coalesce(current_setting('{GUC_EMPRESAS}', true), ''), ','))"
    )


def build_enable_rls_sql(table: str, empresa_column: str = "id_empresa_id") -> str:
    """SQL idempotente para activar RLS forzado y la política en ``table``.

    ``empresa_column`` varía por tabla: ``id_empresa_id`` (FK por defecto de
    Django), ``id_empresa`` (FK con ``db_column``) o ``empresa_id``.
    """
    table = _check_ident(table)
    predicate = _predicate(empresa_column)
    return "\n".join(
        [
            f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;',  # nosec B608
            f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;',  # nosec B608
            f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";',  # nosec B608
            f'CREATE POLICY {POLICY_NAME} ON "{table}"'  # nosec B608
            f"\n    USING ({predicate})"
            f"\n    WITH CHECK ({predicate});",
        ]
    )


def build_disable_rls_sql(table: str) -> str:
    """SQL para revertir lo aplicado por :func:`build_enable_rls_sql`."""
    table = _check_ident(table)
    return "\n".join(
        [
            f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";',  # nosec B608
            f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;',  # nosec B608
            f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;',  # nosec B608
        ]
    )


# --- Runtime: fijar el contexto RLS en la conexión ------------------------


def _set_config(cursor, name: str, value: str) -> None:
    # set_config parametrizado evita problemas de quoting e inyección.
    cursor.execute("SELECT set_config(%s, %s, false)", [name, value])


def apply_context(empresa_ids, *, bypass: bool = False, using: str = DEFAULT_DB_ALIAS) -> None:
    """Fija el contexto RLS (empresas visibles + bypass) en la conexión."""
    csv = ",".join(str(e) for e in empresa_ids) if empresa_ids else ""
    with connections[using].cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, "on" if bypass else "off")
        _set_config(cursor, GUC_EMPRESAS, csv)


def current_role_bypasses_rls(using: str = DEFAULT_DB_ALIAS) -> bool:
    """True si el rol de conexión salta RLS (``SUPERUSER`` o ``BYPASSRLS``).

    Un superusuario o un rol con ``BYPASSRLS`` ignora las políticas RLS aunque
    estén ``FORCE``; en ese caso el aislamiento no es verificable directamente
    (p. ej. el rol ``postgres`` por defecto en CI). Los tests usan esto para,
    cuando aplica, hacer ``SET ROLE`` a un rol no-privilegiado y poder verificar
    el enforcement. En prod, el blocker documentado es conectar la app con un rol
    dedicado no-dueño y sin estos atributos.
    """
    with connections[using].cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        row = cursor.fetchone()
    return bool(row and row[0])


def apply_system_default(using: str = DEFAULT_DB_ALIAS) -> None:
    """Estado por defecto de conexiones no-web: ``bypass='on'``, sin empresas.

    Lo usa el signal ``connection_created`` y el middleware al finalizar cada
    request (para no devolver una conexión "cerrada" a un pool si en el futuro
    se habilita ``CONN_MAX_AGE`` / pgbouncer en *session pooling*).
    """
    with connections[using].cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, "on")
        _set_config(cursor, GUC_EMPRESAS, "")


@contextmanager
def rls_bypass(using: str = DEFAULT_DB_ALIAS):
    """Marca explícita de contexto de sistema con bypass (Celery, comandos,
    data migrations). El default de conexión ya es bypass; este helper lo hace
    explícito y reaplica el default al salir."""
    with connections[using].cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, "on")
    try:
        yield
    finally:
        apply_system_default(using)


# Tablas multi-tenant con RLS forzado (tabla -> columna empresa). Cubre las tres
# variantes de nombre de columna del esquema. El rollout avanza por lotes, un PR
# por grupo de apps (ver docs/planes/05-seguridad-hardening.md, P0-1 follow-up 5).
PILOT_TABLES = {
    # Lote 1 — piloto inicial.
    "sucursales": "id_empresa",
    "ventas_pedido": "id_empresa_id",
    "ventas_nota_venta": "id_empresa_id",
    "ventas_factura_fiscal": "id_empresa_id",
    "finanzas_transaccion_financiera": "id_empresa_id",
    "cxc_gestioncobranza": "empresa_id",
    "cxc_acuerdopago": "empresa_id",
    # Lote 2 — inventario / compras / crm.
    "inventario_producto": "id_empresa_id",
    "inventario_stock_actual": "id_empresa_id",
    "inventario_movimiento_inventario": "id_empresa_id",
    "compras_orden_compra": "id_empresa_id",
    "compras_recepcion_mercancia": "id_empresa_id",
    "crm_cliente": "id_empresa_id",
    "crm_contacto_cliente": "id_empresa_id",
    "crm_direccion_cliente": "id_empresa_id",
}
