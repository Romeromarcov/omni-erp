"""
Fix M3: RecepcionMercancia was created in 0001 without db_table,
so the actual DB table is 'compras_recepcionmercancia'.
The model's Meta.db_table now says 'compras_recepcion_mercancia'.
This migration renames the table to match.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0006_rename_facturacompra_table"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="recepcionmercancia",
            table="compras_recepcion_mercancia",
        ),
    ]
