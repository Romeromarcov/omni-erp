"""RLS lote 2 (P0-1 rollout) — tablas de inventario (columna ``id_empresa_id``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    "inventario_producto",
    "inventario_stock_actual",
    "inventario_movimiento_inventario",
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, "id_empresa_id") for t in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0007_alter_categoriaproducto_id_categoria_producto_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
