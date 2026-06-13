"""RLS lote 3 (CTF-012, P0-1 rollout) — tablas tenant de ``inventario``.

Genera la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes 1 y 2 (ver ``apps/core/rls.py``). ``null_visible=True`` marca los
catálogos compartidos: empresa ``NULL`` = fila global visible por todos.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("inventario_categoria_producto", "id_empresa_id", False),
    ("inventario_conversion_unidad_medida", "id_empresa_id", False),
    ("inventario_requisicion_interna", "id_empresa_id", False),
    ("inventario_stock_consignacion_cliente", "id_empresa_id", False),
    ("inventario_stock_consignacion_proveedor", "id_empresa_id", False),
    ("inventario_unidad_medida", "id_empresa_id", False),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0009_producto_punto_reorden"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
