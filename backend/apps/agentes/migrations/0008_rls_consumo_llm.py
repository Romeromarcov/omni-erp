"""RLS para ``agentes_consumo_llm`` (política ``omni_rls_tenant`` + FORCE + null_visible; Plan 05 P2-3)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("agentes_consumo_llm", "id_empresa_id", True),
]


def _enable() -> str:
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable() -> str:
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("agentes", "0007_consumollm"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
