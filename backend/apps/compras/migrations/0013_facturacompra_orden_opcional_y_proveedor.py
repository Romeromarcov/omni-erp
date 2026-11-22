"""Hace opcional ``FacturaCompra.id_orden_compra``, añade ``FacturaCompra.id_proveedor`` y hace backfill."""

import django.db.models.deletion
from django.db import migrations, models

from apps.core.rls import rls_bypass

_BATCH_SIZE = 500


def _backfill_proveedor_factura_compra(apps, schema_editor):
    FacturaCompra = apps.get_model("compras", "FacturaCompra")
    alias = schema_editor.connection.alias

    with rls_bypass(using=alias):
        base_qs = (
            FacturaCompra.objects.using(alias)
            .filter(
                id_proveedor__isnull=True,
                id_orden_compra__isnull=False,
                id_orden_compra__id_proveedor__isnull=False,
            )
            .select_related("id_orden_compra")
            .order_by("id_factura_compra")
        )
        ultimo_pk = None
        while True:
            chunk_qs = base_qs.filter(id_factura_compra__gt=ultimo_pk) if ultimo_pk is not None else base_qs
            pagina = list(chunk_qs[:_BATCH_SIZE])
            if not pagina:
                break
            ultimo_pk = pagina[-1].id_factura_compra

            lote = []
            for fac in pagina:
                orden = fac.id_orden_compra
                if orden is not None and orden.id_empresa_id == fac.id_empresa_id and orden.id_proveedor_id:
                    fac.id_proveedor_id = orden.id_proveedor_id
                    lote.append(fac)

            if lote:
                FacturaCompra.objects.using(alias).bulk_update(lote, ["id_proveedor"])


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0012_trazabilidad_procurement"),
        ("proveedores", "0006_rls_lote3_proveedores"),
    ]

    operations = [
        migrations.AlterField(
            model_name="facturacompra",
            name="id_orden_compra",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="facturas",
                to="compras.ordencompra",
            ),
        ),
        migrations.AddField(
            model_name="facturacompra",
            name="id_proveedor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="facturas_compra",
                to="proveedores.proveedor",
            ),
        ),
        migrations.RunPython(
            code=_backfill_proveedor_factura_compra,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
