"""RLS para ``contabilidad_diario`` y ``contabilidad_periodo_contable`` (PR-13 / B1)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("contabilidad_diario", "id_empresa_id", False),
    ("contabilidad_periodo_contable", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("contabilidad", "0016_diariocontable_periodocontable_y_asientos"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
