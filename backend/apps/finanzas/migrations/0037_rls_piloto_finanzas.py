"""RLS piloto (P0-1) — ``finanzas_transaccion_financiera`` (col ``id_empresa_id``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLE = "finanzas_transaccion_financiera"


class Migration(migrations.Migration):

    dependencies = [
        ("finanzas", "0036_alter_caja_id_caja_alter_cajafisica_id_caja_fisica_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=build_enable_rls_sql(_TABLE, "id_empresa_id"),
            reverse_sql=build_disable_rls_sql(_TABLE),
        ),
    ]
