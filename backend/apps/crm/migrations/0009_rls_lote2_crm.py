"""RLS lote 2 (P0-1 rollout) — tablas de crm (columna ``id_empresa_id``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    "crm_cliente",
    "crm_contacto_cliente",
    "crm_direccion_cliente",
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, "id_empresa_id") for t in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0008_alter_cliente_dias_credito_alter_cliente_id_cliente_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
