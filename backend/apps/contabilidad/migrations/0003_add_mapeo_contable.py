import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contabilidad", "0002_initial"),
        ("core", "0010_base_model_empresa_sucursal_departamento"),
    ]

    operations = [
        migrations.CreateModel(
            name="MapeoContable",
            fields=[
                ("id_mapeo", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "tipo_asiento",
                    models.CharField(
                        choices=[
                            ("FACTURA_VENTA", "Factura de Venta"),
                            ("FACTURA_COMPRA", "Factura de Compra"),
                            ("RECEPCION_MERCANCIA", "Recepción de Mercancía"),
                            ("AJUSTE_INVENTARIO", "Ajuste de Inventario"),
                            ("SALIDA_INTERNA", "Salida Interna / Requisición"),
                            ("PAGO_CXC", "Pago de Cuenta por Cobrar"),
                            ("PAGO_CXP", "Pago de Cuenta por Pagar"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "descripcion_plantilla",
                    models.CharField(default="{tipo} - {numero}", max_length=255),
                ),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                (
                    "cuenta_debe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mapeos_debe",
                        to="contabilidad.plancuentas",
                    ),
                ),
                (
                    "cuenta_haber",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mapeos_haber",
                        to="contabilidad.plancuentas",
                    ),
                ),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mapeos_contables",
                        to="core.empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "Mapeo Contable",
                "verbose_name_plural": "Mapeos Contables",
                "db_table": "contabilidad_mapeo_contable",
            },
        ),
        migrations.AlterUniqueTogether(
            name="mapeocontable",
            unique_together={("id_empresa", "tipo_asiento")},
        ),
    ]
