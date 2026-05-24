"""
Migración: Cliente, ContactoCliente, DireccionCliente → OmniBaseModel.
- Bug fix: rif de Cliente pasa de unique global a unique_together por empresa.
- Validador de teléfono más permisivo (acepta fijos y formatos internacionales).
"""

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0003_alter_cliente_options"),
        ("core", "0010_base_model_empresa_sucursal_departamento"),
    ]

    operations = [
        # ── Cliente ───────────────────────────────────────────────────────────

        migrations.AddField(
            model_name="cliente",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="cliente",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="cliente",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="cliente",
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
            model_name="cliente",
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
            model_name="cliente",
            name="rif",
            field=models.CharField(max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name="cliente",
            unique_together={("id_empresa", "rif")},
        ),

        # ── ContactoCliente ───────────────────────────────────────────────────

        migrations.AddField(
            model_name="contactocliente",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="contactocliente",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="contactocliente",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),

        # ── DireccionCliente ──────────────────────────────────────────────────

        migrations.AddField(
            model_name="direccioncliente",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="direccioncliente",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="direccioncliente",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
    ]
