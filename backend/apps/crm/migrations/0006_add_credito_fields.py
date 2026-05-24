from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0005_alter_cliente_id_empresa_alter_cliente_rif"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="tipo_cliente",
            field=models.CharField(
                max_length=10,
                choices=[("CONTADO", "Contado"), ("CREDITO", "Crédito")],
                default="CONTADO",
                verbose_name="Tipo de cliente",
            ),
        ),
        migrations.AddField(
            model_name="cliente",
            name="limite_credito",
            field=models.DecimalField(
                max_digits=18,
                decimal_places=2,
                default=0,
                verbose_name="Límite de crédito",
                help_text="Límite de crédito aprobado. 0 = sin límite definido.",
            ),
        ),
        migrations.AddField(
            model_name="cliente",
            name="dias_credito",
            field=models.PositiveSmallIntegerField(
                default=0,
                verbose_name="Días de crédito",
                help_text="Días de plazo de crédito.",
            ),
        ),
    ]
