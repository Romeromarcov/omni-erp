"""
0004_empresa_not_null_manufactura.py

CTF-004: Hace que el campo empresa sea NOT NULL en ListaMateriales,
RutaProduccion y OrdenProduccion, completando el multi-tenancy en manufactura.

Prerequisito: todos los registros existentes deben tener empresa asignada.
Si la BD de producción tiene registros huérfanos, ejecutar primero:
    UPDATE manufactura_listamateriales SET empresa_id = <default_uuid> WHERE empresa_id IS NULL;
    UPDATE manufactura_rutaproduccion SET empresa_id = <default_uuid> WHERE empresa_id IS NULL;
    UPDATE manufactura_ordenproduccion SET empresa_id = <default_uuid> WHERE empresa_id IS NULL;
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("manufactura", "0003_fix_nullable_string_fields"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="listamateriales",
            name="empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="core.empresa",
            ),
        ),
        migrations.AlterField(
            model_name="rutaproduccion",
            name="empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="core.empresa",
            ),
        ),
        migrations.AlterField(
            model_name="ordenproduccion",
            name="empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="core.empresa",
            ),
        ),
    ]
