"""RLS para ``inventario_regla_reabastecimiento`` e ``inventario_lote_producto``.

Aplica la política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` (ver
``apps/core/rls.py``). ``inventario_movimiento_lote`` se aísla vía sus FKs
(``MovimientoInventario`` y ``LoteProducto``), análogo a ``OperacionInventarioLinea``.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("inventario_regla_reabastecimiento", "id_empresa_id", False),
    ("inventario_lote_producto", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0018_producto_estrategia_salida_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
