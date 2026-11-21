"""RLS de ``crm_actividad`` (Omni Connect, S4).

Política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` (ver ``apps/core/rls.py``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLE = "crm_actividad"
_EMPRESA_COL = "id_empresa_id"


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0013_actividad"),
    ]

    operations = [
        migrations.RunSQL(
            sql=build_enable_rls_sql(_TABLE, _EMPRESA_COL, null_visible=False),
            reverse_sql=build_disable_rls_sql(_TABLE),
        ),
    ]
