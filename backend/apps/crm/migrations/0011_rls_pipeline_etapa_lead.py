"""RLS del CRM ligero (Omni Connect, S1) — ``crm_pipeline``, ``crm_etapa``, ``crm_lead``.

Misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` que los lotes
1–3 (ver ``apps/core/rls.py``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("crm_pipeline", "id_empresa_id", False),
    ("crm_etapa", "id_empresa_id", False),
    ("crm_lead", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0010_pipeline_etapa_lead"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
