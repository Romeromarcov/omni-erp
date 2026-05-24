import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_contacto_data_migration"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConfiguracionFlujoDocumentos",
            fields=[
                (
                    "id_configuracion",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("activo", models.BooleanField(default=True)),
                (
                    "tipo_documento",
                    models.CharField(
                        choices=[("VENTAS", "Ciclo de Ventas"), ("COMPRAS", "Ciclo de Compras")],
                        max_length=10,
                    ),
                ),
                (
                    "paso",
                    models.CharField(
                        choices=[
                            ("COTIZACION", "Cotización"),
                            ("PEDIDO", "Pedido / Nota de Venta"),
                            ("NOTA_ENTREGA", "Nota de Entrega"),
                            ("FACTURA", "Factura Fiscal"),
                            ("SOLICITUD", "Solicitud de Compra"),
                            ("ORDEN_COMPRA", "Orden de Compra"),
                            ("RECEPCION", "Recepción de Mercancía"),
                            ("FACTURA_COMPRA", "Factura de Compra"),
                        ],
                        max_length=20,
                    ),
                ),
                ("obligatorio", models.BooleanField(default=True)),
                ("orden", models.PositiveSmallIntegerField(default=1)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configuraciones_flujo",
                        to="core.empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "Configuración de Flujo de Documentos",
                "verbose_name_plural": "Configuraciones de Flujo de Documentos",
                "db_table": "core_configuracion_flujo_documentos",
                "ordering": ["tipo_documento", "orden"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="configuracionflujodocumentos",
            unique_together={("id_empresa", "tipo_documento", "paso")},
        ),
    ]
