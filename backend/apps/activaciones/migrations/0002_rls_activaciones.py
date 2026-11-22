"""RLS de las tablas tenant de ``activaciones`` (política ``omni_rls_tenant`` + FORCE; ver ``apps/core/rls.py``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("activaciones_calendario", "id_empresa_id", False),
    ("activaciones_recurso", "id_empresa_id", False),
    ("activaciones_evento", "id_empresa_id", False),
    ("activaciones_uso_recurso", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [("activaciones", "0001_inicial")]

    operations = [migrations.RunSQL(sql=_enable(), reverse_sql=_disable())]
