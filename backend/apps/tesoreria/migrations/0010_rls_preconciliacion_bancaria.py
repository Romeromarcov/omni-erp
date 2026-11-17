"""RLS para las tablas de pre-conciliación bancaria (R-CODE-1 / P0-1)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("tesoreria_configuracion_conciliacion_cuenta", "id_empresa_id", False),
    ("tesoreria_propuesta_conciliacion_bancaria", "id_empresa_id", False),
    ("tesoreria_decision_preconciliacion_bancaria", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("tesoreria", "0009_preconciliacion_bancaria_modelos"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
