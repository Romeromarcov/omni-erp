"""
Migración: Inventario → OmniBaseModel / TimeStampedModel.

Modelos actualizados:
  - UnidadMedida, CategoriaProducto, VarianteProducto: agregan fecha_creacion + fecha_actualizacion
  - Producto, ConversionUnidadMedida: agregan fecha_actualizacion
  - MovimientoInventario, StockConsignacionCliente, StockConsignacionProveedor: agregan fecha_actualizacion
"""

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0002_alter_producto_options_alter_unidadmedida_options_and_more"),
        ("core", "0010_base_model_empresa_sucursal_departamento"),
    ]

    operations = [
        # ── UnidadMedida: agregar timestamps ──────────────────────────────────

        migrations.AddField(
            model_name="unidadmedida",
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
            model_name="unidadmedida",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="unidadmedida",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="unidadmedida",
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
            model_name="unidadmedida",
            name="documento_json",
            field=models.JSONField(
                null=True,
                blank=True,
                verbose_name="Documento JSON",
                help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
            ),
        ),

        # ── CategoriaProducto: agregar timestamps ─────────────────────────────

        migrations.AddField(
            model_name="categoriaproducto",
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
            model_name="categoriaproducto",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="categoriaproducto",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="categoriaproducto",
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
            model_name="categoriaproducto",
            name="documento_json",
            field=models.JSONField(
                null=True,
                blank=True,
                verbose_name="Documento JSON",
                help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
            ),
        ),

        # ── Producto: agregar fecha_actualizacion ─────────────────────────────

        migrations.AddField(
            model_name="producto",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="producto",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="producto",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),
        migrations.AlterField(
            model_name="producto",
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
            model_name="producto",
            name="documento_json",
            field=models.JSONField(
                null=True,
                blank=True,
                verbose_name="Documento JSON",
                help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
            ),
        ),

        # ── VarianteProducto: agregar timestamps ──────────────────────────────

        migrations.AddField(
            model_name="varianteproducto",
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
            model_name="varianteproducto",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="varianteproducto",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),

        # ── MovimientoInventario: agregar fecha_actualizacion ─────────────────

        migrations.AddField(
            model_name="movimientoinventario",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="movimientoinventario",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),

        # ── ConversionUnidadMedida: agregar fecha_actualizacion ───────────────

        migrations.AddField(
            model_name="conversionunidadmedida",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="conversionunidadmedida",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="conversionunidadmedida",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
                help_text="Indica si el registro está activo (False = borrado lógico).",
            ),
        ),

        # ── StockConsignacionCliente: agregar fecha_actualizacion ─────────────

        migrations.AddField(
            model_name="stockconsignacioncliente",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="stockconsignacioncliente",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),

        # ── StockConsignacionProveedor: agregar fecha_actualizacion ───────────

        migrations.AddField(
            model_name="stockconsignacionproveedor",
            name="fecha_actualizacion",
            field=models.DateTimeField(
                auto_now=True,
                verbose_name="Fecha de Actualización",
                help_text="Fecha y hora de la última modificación del registro.",
            ),
        ),
        migrations.AlterField(
            model_name="stockconsignacionproveedor",
            name="fecha_creacion",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Fecha de Creación",
                help_text="Fecha y hora de creación del registro.",
            ),
        ),
    ]
