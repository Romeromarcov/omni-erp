"""
Migration: Rename field es_superusuario_innova → es_superusuario_omni
Part of the project rebranding from InnovaERP to Omni ERP.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_fix_sesion_caja_unique_constraint'),
    ]

    operations = [
        migrations.RenameField(
            model_name='usuarios',
            old_name='es_superusuario_innova',
            new_name='es_superusuario_omni',
        ),
    ]
