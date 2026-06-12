"""RLS lote 3 (CTF-012, P0-1 rollout) — tablas tenant de ``core``.

Genera la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes 1 y 2 (ver ``apps/core/rls.py``). ``null_visible=True`` marca los
catálogos compartidos: empresa ``NULL`` = fila global visible por todos.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("core_capability_token", "empresa_id", False),
    ("core_clave_idempotencia", "empresa_id", False),
    ("core_configuracion_flujo_documentos", "id_empresa_id", False),
    ("core_contacto", "id_empresa_id", False),
    ("core_dispositivo", "empresa_id", False),
    ("core_notificacion", "id_empresa_id", False),
    ("departamentos", "id_empresa", False),
    ("registro_auditoria", "id_empresa", False),
    ("roles", "id_empresa", True),
    ("usuarios_empresas", "empresa_id", False),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_claveidempotencia_usuario_ttl"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
