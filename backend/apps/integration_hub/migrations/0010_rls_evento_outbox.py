"""RLS de ``integration_hub_evento_outbox`` (Omni Connect, S7).

Política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` (ver ``apps/core/rls.py``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLE = "integration_hub_evento_outbox"
_EMPRESA_COL = "id_empresa_id"


class Migration(migrations.Migration):
    dependencies = [
        ("integration_hub", "0009_evento_outbox"),
    ]

    operations = [
        migrations.RunSQL(
            sql=build_enable_rls_sql(_TABLE, _EMPRESA_COL, null_visible=False),
            reverse_sql=build_disable_rls_sql(_TABLE),
        ),
    ]
