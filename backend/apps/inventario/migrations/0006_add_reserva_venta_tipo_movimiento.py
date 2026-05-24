"""
0006_add_reserva_venta_tipo_movimiento.py

Agrega RESERVA_VENTA a las choices de MovimientoInventario.tipo_movimiento.
Es un tipo informativo (Sprint 0.H): registra el audit trail de la reserva de
stock creada en confirmar_pedido() sin alterar cantidad_disponible.

Django no impone choices a nivel de base de datos, por lo que esta migración
solo actualiza los metadatos del modelo para que makemigrations quede limpio.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0005_add_salida_interna_requisicion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="movimientoinventario",
            name="tipo_movimiento",
            field=models.CharField(
                max_length=50,
                choices=[
                    ("ENTRADA", "Entrada"),
                    ("SALIDA", "Salida"),
                    ("TRANSFERENCIA", "Transferencia"),
                    ("AJUSTE", "Ajuste"),
                    ("CONSUMO_PRODUCCION", "Consumo Producción"),
                    ("RECEPCION_COMPRA", "Recepción Compra"),
                    ("DESPACHO_VENTA", "Despacho Venta"),
                    ("SALIDA_INTERNA", "Salida Interna"),
                    ("RESERVA_VENTA", "Reserva de Venta"),
                ],
            ),
        ),
    ]
