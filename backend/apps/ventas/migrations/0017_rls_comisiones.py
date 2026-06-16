"""RLS para las tablas tenant de comisiones de venta (R-CODE-1).

Aplica la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes anteriores (ver ``apps/core/rls.py``) a las tablas con FK directo a
``core.Empresa`` introducidas por las comisiones de venta. La tabla hija
``ventas_esquema_comision_categoria`` no lleva política propia: no tiene columna
de empresa y queda protegida vía su FK al esquema padre (mismo patrón que las
tablas ``ventas_detalle_*``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("ventas_esquema_comision", "id_empresa_id", False),
    ("ventas_comision_venta", "id_empresa_id", False),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0016_notaventa_id_vendedor_pedido_id_vendedor_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
