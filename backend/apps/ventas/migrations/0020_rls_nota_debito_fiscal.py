"""RLS para la tabla tenant de notas de débito fiscales (R-CODE-1).

Aplica la política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` sobre
``ventas_nota_debito_fiscal``. La tabla hija ``ventas_detalle_nota_debito_fiscal``
queda protegida vía su FK a ``ventas_nota_debito_fiscal`` (mismo patrón que
``ventas_detalle_nota_credito_fiscal``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("ventas_nota_debito_fiscal", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0019_notaventa_ambito_notadebitofiscal_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
