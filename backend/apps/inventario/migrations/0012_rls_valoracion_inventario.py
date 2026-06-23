"""RLS para ``inventario_valoracion_inventario`` (capas de costo FIFO/Promedio).

Aplica la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes 1–3 (ver ``apps/core/rls.py``). Tabla transaccional (no catálogo
compartido) → ``null_visible=False``.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("inventario_valoracion_inventario", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0011_producto_metodo_valoracion_valoracioninventario"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
