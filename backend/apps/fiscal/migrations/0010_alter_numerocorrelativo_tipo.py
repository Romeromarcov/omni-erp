from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0009_rls_lote3_fiscal"),
    ]

    operations = [
        migrations.AlterField(
            model_name="numerocorrelativo",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("FACTURA", "Factura Fiscal"),
                    ("NOTA_DEBITO", "Nota de Débito"),
                    ("NOTA_CREDITO", "Nota de Crédito"),
                    ("NOTA_ENTREGA", "Nota de Entrega"),
                    ("ORDEN_COMPRA", "Orden de Compra"),
                    ("DESPACHO", "Despacho"),
                ],
                max_length=20,
            ),
        ),
    ]
