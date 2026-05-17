from django.db import migrations


class Migration(migrations.Migration):
    """Rename compras_facturacompra → compras_factura_compra to match Meta.db_table."""

    dependencies = [
        ("compras", "0005_facturacompra_id_empresa_not_null"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="facturacompra",
            table="compras_factura_compra",
        ),
    ]
