"""RLS para ``inventario_operacion_inventario`` (operaciones con stepper).

Las tablas hijas (paso, línea) no tienen FK directa a Empresa: su aislamiento es
vía la operación padre. Aplica ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY``.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("inventario_operacion_inventario", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0015_operacioninventario_operacioninventariolinea_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
