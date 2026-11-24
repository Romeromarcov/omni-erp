"""RLS para tablas de Portales Clientes/Vendedores en ventas (Plan 09 Fase 7.2-7.3)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("ventas_token_portal_cliente", "id_empresa_id", False),
    ("ventas_pago_portal_cliente", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("ventas", "0023_pagoportalcliente_tokenportalcliente"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
