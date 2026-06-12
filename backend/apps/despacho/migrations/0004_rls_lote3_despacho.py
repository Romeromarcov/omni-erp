"""RLS lote 3 (P0-1 rollout) — tabla de despacho (columna ``id_empresa_id``).

``despacho_detalle_despacho`` no se incluye: no tiene columna de empresa
(pertenece vía id_despacho→Despacho), igual que el resto de tablas "detalle"
del rollout; su aislamiento lo aplica la capa de aplicación (R-CODE-1).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    "despacho_despacho",
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, "id_empresa_id") for t in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("despacho", "0003_alter_despacho_options_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
