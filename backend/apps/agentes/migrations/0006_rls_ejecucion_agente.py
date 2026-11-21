"""RLS para ``agentes_ejecucion_agente`` (política ``omni_rls_tenant`` + FORCE; Plan 05 P2-2)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("agentes_ejecucion_agente", "id_empresa_id", False),
]


def _enable() -> str:
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable() -> str:
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("agentes", "0005_ejecucionagente"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
