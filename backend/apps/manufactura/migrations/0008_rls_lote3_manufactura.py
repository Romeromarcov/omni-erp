"""RLS lote 3 (CTF-012, P0-1 rollout) — tablas tenant de ``manufactura``.

Genera la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes 1 y 2 (ver ``apps/core/rls.py``). ``null_visible=True`` marca los
catálogos compartidos: empresa ``NULL`` = fila global visible por todos.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("manufactura_centro_trabajo", "id_empresa_id", False),
    ("manufactura_configuracion", "empresa_id", False),
    ("manufactura_etapa_produccion", "empresa_id", False),
    ("manufactura_listamateriales", "empresa_id", False),
    ("manufactura_operacion_produccion", "id_empresa_id", False),
    ("manufactura_ordenproduccion", "empresa_id", False),
    ("manufactura_rutaproduccion", "empresa_id", False),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("manufactura", "0007_consumomaterial_costo_unitario_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
