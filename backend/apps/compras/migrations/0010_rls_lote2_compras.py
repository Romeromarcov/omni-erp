"""RLS lote 2 (P0-1 rollout) — tablas de compras (columna ``id_empresa_id``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    "compras_orden_compra",
    "compras_recepcion_mercancia",
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, "id_empresa_id") for t in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0009_alter_facturacompra_options_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
