"""
Migración: Empresa, Sucursal, Departamento → OmniBaseModel + IntegrationFieldsMixin.

Cambios:
  Empresa:
    - RenameField fecha_registro → fecha_creacion
    - AddField fecha_actualizacion (auto_now)
    - AlterField activo (remove db_index, add verbose_name/help_text)
    - AlterField referencia_externa, documento_json (add verbose_name/help_text)
  Sucursal:
    - AddField fecha_actualizacion (auto_now)
    - AlterField activo, fecha_creacion, referencia_externa, documento_json
  Departamento:
    - AddField fecha_creacion (auto_now_add, one-time default=timezone.now)
    - AddField fecha_actualizacion (auto_now)
    - AlterField activo, referencia_externa, documento_json
"""

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_add_capability_token"),
    ]

    operations = [
        # ── Empresa ──────────────────────────────────────────────────────────

        migrations.RenameField(
            model_name="empresa",
            old_name="fecha_registro",
            new_name="fecha_creacion",
        ),
        migrations.AlterField(
            model_name="empresa",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="referencia_externa",
            field=models.CharField(
                max_length=100,
                null=True,
                blank=True,
                verbose_name="Referencia externa",
                help_text="Identificador del registro en el sistema externo de origen.",
            ),
        ),
        migrations.AlterField(
            model_name="empresa",
            name="documento_json",
            field=models.JSONField(
                null=True,
                blank=True,
                verbose_name="Documento JSON",
                help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
            ),
        ),

        # ── Sucursal ─────────────────────────────────────────────────────────

        migrations.AddField(
            model_name="sucursal",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="sucursal",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="sucursal",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="sucursal",
            name="referencia_externa",
            field=models.CharField(
                max_length=100,
                null=True,
                blank=True,
                verbose_name="Referencia externa",
                help_text="Identificador del registro en el sistema externo de origen.",
            ),
        ),
        migrations.AlterField(
            model_name="sucursal",
            name="documento_json",
            field=models.JSONField(
                null=True,
                blank=True,
                verbose_name="Documento JSON",
                help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
            ),
        ),

        # ── Departamento ─────────────────────────────────────────────────────

        migrations.AddField(
            model_name="departamento",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="departamento",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="departamento",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="departamento",
            name="referencia_externa",
            field=models.CharField(
                max_length=100,
                null=True,
                blank=True,
                verbose_name="Referencia externa",
                help_text="Identificador del registro en el sistema externo de origen.",
            ),
        ),
        migrations.AlterField(
            model_name="departamento",
            name="documento_json",
            field=models.JSONField(
                null=True,
                blank=True,
                verbose_name="Documento JSON",
                help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
            ),
        ),
    ]
