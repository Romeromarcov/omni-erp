"""
Make FacturaCompra.id_empresa non-nullable now that all existing rows have been backfilled.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0004_recepcion_detalle_factura_update"),
        ("core", "0011_empresa_contabilidad_auto_aprobar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="facturacompra",
            name="id_empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="facturas_compra",
                to="core.empresa",
            ),
        ),
    ]
