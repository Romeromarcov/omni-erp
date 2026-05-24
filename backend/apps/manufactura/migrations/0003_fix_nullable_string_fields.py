"""
0003_fix_nullable_string_fields.py

Removes excess null=True from CharField, TextField and JSONField columns
(R-CODE-10). String-based fields use empty string as the empty state;
JSON fields use an empty dict. Nullable DateField/DateTimeField and FK
fields with SET_NULL are intentionally left as-is.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("manufactura", "0002_fix_codigo_unique_per_empresa"),
    ]

    operations = [
        # ListaMateriales
        migrations.AlterField(
            model_name="listamateriales",
            name="referencia_externa",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="listamateriales",
            name="documento_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="listamateriales",
            name="descripcion",
            field=models.TextField(blank=True, default=""),
        ),
        # RutaProduccion
        migrations.AlterField(
            model_name="rutaproduccion",
            name="referencia_externa",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="rutaproduccion",
            name="documento_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="rutaproduccion",
            name="descripcion",
            field=models.TextField(blank=True, default=""),
        ),
        # OrdenProduccion
        migrations.AlterField(
            model_name="ordenproduccion",
            name="referencia_externa",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="ordenproduccion",
            name="documento_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="ordenproduccion",
            name="tipo_operacion",
            field=models.CharField(max_length=50, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="ordenproduccion",
            name="observaciones",
            field=models.TextField(blank=True, default=""),
        ),
        # ConsumoMaterial
        migrations.AlterField(
            model_name="consumomaterial",
            name="referencia_externa",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="consumomaterial",
            name="documento_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        # ProduccionTerminada
        migrations.AlterField(
            model_name="produccionterminada",
            name="referencia_externa",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="produccionterminada",
            name="documento_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        # ListaMaterialesDetalle
        migrations.AlterField(
            model_name="listamaterialesdetalle",
            name="observaciones",
            field=models.TextField(blank=True, default=""),
        ),
        # CentroTrabajo
        migrations.AlterField(
            model_name="centrotrabajo",
            name="descripcion",
            field=models.TextField(blank=True, default=""),
        ),
        # OperacionProduccion
        migrations.AlterField(
            model_name="operacionproduccion",
            name="descripcion",
            field=models.TextField(blank=True, default=""),
        ),
        # RutaProduccionDetalle
        migrations.AlterField(
            model_name="rutaproducciondetalle",
            name="observaciones",
            field=models.TextField(blank=True, default=""),
        ),
        # RegistroOperacion
        migrations.AlterField(
            model_name="registrooperacion",
            name="observaciones",
            field=models.TextField(blank=True, default=""),
        ),
    ]
