"""
Migración: Proveedor, ContactoProveedor, CuentaBancariaProveedor → OmniBaseModel.
- Bug fix: rif de Proveedor pasa de unique global a unique_together por empresa.
"""

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proveedores", "0001_initial"),
        ("core", "0010_base_model_empresa_sucursal_departamento"),
    ]

    operations = [
        # ── Proveedor ─────────────────────────────────────────────────────────

        migrations.AddField(
            model_name="proveedor",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="proveedor",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="proveedor",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="proveedor",
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
            model_name="proveedor",
            name="documento_json",
            field=models.JSONField(
                null=True,
                blank=True,
                verbose_name="Documento JSON",
                help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
            ),
        ),
        # RIF: quitar unique global, pasar a unique_together por empresa
        migrations.AlterField(
            model_name="proveedor",
            name="rif",
            field=models.CharField(max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name="proveedor",
            unique_together={("id_empresa", "rif")},
        ),

        # ── ContactoProveedor ─────────────────────────────────────────────────

        migrations.AddField(
            model_name="contactoproveedor",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="contactoproveedor",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="contactoproveedor",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),

        # ── CuentaBancariaProveedor ───────────────────────────────────────────

        migrations.AddField(
            model_name="cuentabancariaproveedor",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="cuentabancariaproveedor",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="cuentabancariaproveedor",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
    ]
