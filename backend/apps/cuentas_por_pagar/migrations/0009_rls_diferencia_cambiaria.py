"""RLS para ``cuentas_por_pagar_diferencia_cambiaria`` (R-CODE-1).

El nuevo modelo ``DiferenciaCambiaria`` tiene FK a Empresa, así que requiere la
misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` que el resto
de las tablas tenant (ver ``apps/core/rls.py`` y el lote 3 de CxP en
``0006_rls_lote3_cuentas_por_pagar``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("cuentas_por_pagar_diferencia_cambiaria", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas_por_pagar", "0008_diferenciacambiaria"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
