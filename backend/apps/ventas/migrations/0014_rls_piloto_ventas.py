"""RLS piloto (P0-1) — tablas de ventas (columna ``id_empresa_id``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = ["ventas_pedido", "ventas_nota_venta", "ventas_factura_fiscal"]


def _enable():
    return "\n".join(build_enable_rls_sql(t, "id_empresa_id") for t in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0013_alter_cotizacion_id_cotizacion_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
