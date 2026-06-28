"""RLS (Row Level Security) para las tablas tenant de ``cxc_lubrikca``.

Aplica la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` que el
resto del ERP (ver ``apps/core/rls.py``). Todas las tablas tienen FK ``empresa``
(columna ``empresa_id``) y no admiten filas globales (``null_visible=False``).
Defensa en profundidad sobre el filtrado por ``get_empresas_visible`` (R-CODE-1).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("cxc_lubrikca_descuentomarcacategoria", "empresa_id", False),
    ("cxc_lubrikca_descuentobcvcompleto", "empresa_id", False),
    ("cxc_lubrikca_promocionprimeracompra", "empresa_id", False),
    ("cxc_lubrikca_reglarecurrencia", "empresa_id", False),
    ("cxc_lubrikca_feriado", "empresa_id", False),
    ("cxc_lubrikca_metodopago", "empresa_id", False),
    ("cxc_lubrikca_pedidolubrikca", "empresa_id", False),
    ("cxc_lubrikca_lineapedidolubrikca", "empresa_id", False),
    ("cxc_lubrikca_preciolistalubrikca", "empresa_id", False),
    ("cxc_lubrikca_pagolubrikca", "empresa_id", False),
    ("cxc_lubrikca_vinculacion", "empresa_id", False),
    ("cxc_lubrikca_bandejafacturacion", "empresa_id", False),
    ("cxc_lubrikca_configuracionconciliacion", "empresa_id", False),
    ("cxc_lubrikca_conciliacionlubrikca", "empresa_id", False),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("cxc_lubrikca", "0003_pedidolubrikca_ncs_facturadas_conciliacionlubrikca_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
