"""
Make id_factura_compra nullable on CuentaPorPagar.

The service registrar_recepcion() creates a CxP at reception time,
before the supplier invoice exists. The FK is later filled in by
registrar_factura_compra().
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas_por_pagar", "0003_add_abono_cxp"),
        ("compras", "0007_rename_recepcionmercancia_table"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cuentaporpagar",
            name="id_factura_compra",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cuentas_por_pagar",
                to="compras.facturacompra",
            ),
        ),
    ]
