"""RLS para tablas de conteo físico de inventario (Plan 09 Fase 5.3)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("inventario_conteo", "id_empresa_id", False),
    ("inventario_linea_conteo", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0021_operacioninventariolinea_cantidad_escaneada_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
