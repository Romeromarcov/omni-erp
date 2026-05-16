"""
Agrega campos faltantes a RecepcionMercancia, DetalleRecepcionMercancia y FacturaCompra
para soportar el ciclo completo de compras con asientos automáticos (R-CODE-11).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0003_alter_ordencompra_options_and_more"),
        ("core", "0011_empresa_contabilidad_auto_aprobar"),
    ]

    operations = [
        # ── RecepcionMercancia ────────────────────────────────────────────────
        migrations.AddField(
            model_name="recepcionmercancia",
            name="id_empresa",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="recepciones_mercancia",
                to="core.empresa",
            ),
        ),
        migrations.AddField(
            model_name="recepcionmercancia",
            name="monto_total",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=18),
        ),
        # ── DetalleRecepcionMercancia — campos de costo ───────────────────────
        migrations.AddField(
            model_name="detallerecepcionmercancia",
            name="costo_unitario",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name="detallerecepcionmercancia",
            name="subtotal",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=18),
        ),
        # ── FacturaCompra — id_empresa + FK recepcion ─────────────────────────
        migrations.AddField(
            model_name="facturacompra",
            name="id_empresa",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="facturas_compra",
                to="core.empresa",
            ),
        ),
        migrations.AddField(
            model_name="facturacompra",
            name="id_recepcion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="facturas",
                to="compras.recepcionmercancia",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="facturacompra",
            unique_together={("id_empresa", "numero_factura")},
        ),
    ]
