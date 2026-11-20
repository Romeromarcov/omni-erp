"""RLS para ``almacenes_stock_ubicacion`` (stock por ubicación interna).

Aplica la política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` (ver
``apps/core/rls.py``). Tabla aislada por ``id_empresa_id`` (``null_visible=False``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("almacenes_stock_ubicacion", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("almacenes", "0006_almacen_usa_ubicaciones_stockubicacion"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
