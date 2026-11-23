"""RLS para la tabla tenant de políticas de acceso RBAC/ABAC por rol (R-CODE-1).

Aplica la política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` sobre
``core_politica_acceso_rol`` acotada a ``id_empresa``.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("core_politica_acceso_rol", "id_empresa", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0030_politica_acceso_rol_y_auditoria"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
