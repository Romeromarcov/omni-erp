"""
Fix: recepcionmercancia.id_empresa was added as nullable in 0004.
The model already enforces NOT NULL — align the migration state.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0007_rename_recepcionmercancia_table"),
        ("core", "0011_empresa_contabilidad_auto_aprobar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recepcionmercancia",
            name="id_empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="recepciones_mercancia",
                to="core.empresa",
            ),
        ),
    ]
