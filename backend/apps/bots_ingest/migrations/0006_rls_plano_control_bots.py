"""RLS de las tablas del plano de control de ``bots_ingest`` (política ``omni_rls_tenant`` + FORCE)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("bots_ingest_registro", "id_empresa_id", False),
    ("bots_ingest_latido", "id_empresa_id", False),
    ("bots_ingest_bitacora", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [("bots_ingest", "0005_plano_control_bots")]

    operations = [migrations.RunSQL(sql=_enable(), reverse_sql=_disable())]
