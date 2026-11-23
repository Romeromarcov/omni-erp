"""RLS para la tabla tenant de reglas de precio dinámico (R-CODE-1).

Aplica la política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` sobre
``ventas_regla_precio_dinamico``.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("ventas_regla_precio_dinamico", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0021_reglapreciodinamico_comisionventa_moneda_cobro_tipo_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
