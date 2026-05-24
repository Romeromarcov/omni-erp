from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_base_model_empresa_sucursal_departamento"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="contabilidad_auto_aprobar",
            field=models.BooleanField(
                default=False,
                help_text="Si True, los asientos contables generados automáticamente se aprueban de inmediato.",
            ),
        ),
    ]
