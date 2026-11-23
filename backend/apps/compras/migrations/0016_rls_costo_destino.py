"""RLS para tablas de Costos en Destino / Landed Costs (Plan 09 Fase 5.1)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("compras_costo_destino", "id_empresa_id", False),
    ("compras_linea_costo_destino", "id_empresa_id", False),
    ("compras_asignacion_costo_destino", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0015_costodestino_asignacioncostodestino_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
