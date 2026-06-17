# Generated for POS devoluciones — agrega tipos de asiento de devolución.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contabilidad", "0010_rls_lote3_contabilidad"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mapeocontable",
            name="tipo_asiento",
            field=models.CharField(
                choices=[
                    ("FACTURA_VENTA", "Factura de Venta"),
                    ("DEVOLUCION_VENTA", "Devolución de Venta"),
                    ("DEVOLUCION_VENTA_IVA", "IVA de Devolución de Venta"),
                    ("FACTURA_COMPRA", "Factura de Compra"),
                    ("RECEPCION_MERCANCIA", "Recepción de Mercancía"),
                    ("AJUSTE_INVENTARIO", "Ajuste de Inventario"),
                    ("SALIDA_INTERNA", "Salida Interna / Requisición"),
                    ("PAGO_CXC", "Pago de Cuenta por Cobrar"),
                    ("PAGO_CXP", "Pago de Cuenta por Pagar"),
                    ("NOMINA", "Proceso de Nómina"),
                    ("CAMBIO_DIVISA", "Cambio de Divisa"),
                    ("PAGO_TERCERO", "Pago de Terceros"),
                    ("PAGO_PARAFISCAL", "Pago de Contribución Parafiscal"),
                ],
                max_length=30,
            ),
        ),
    ]
