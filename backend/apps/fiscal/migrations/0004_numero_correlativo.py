import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0003_add_fiscal_ve_config"),
        ("core", "0010_base_model_empresa_sucursal_departamento"),
    ]

    operations = [
        migrations.CreateModel(
            name="NumeroCorrelativo",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="numeraciones",
                        to="core.empresa",
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("FACTURA", "Factura Fiscal"),
                            ("NOTA_DEBITO", "Nota de Débito"),
                            ("NOTA_CREDITO", "Nota de Crédito"),
                            ("NOTA_ENTREGA", "Nota de Entrega"),
                            ("ORDEN_COMPRA", "Orden de Compra"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "prefijo",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text='e.g. "FAC-2026-"',
                        max_length=20,
                    ),
                ),
                ("numero_actual", models.PositiveIntegerField(default=0)),
                (
                    "digitos",
                    models.PositiveSmallIntegerField(
                        default=8,
                        help_text="Pad width, e.g. 8 → 00000001",
                    ),
                ),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "fiscal_numero_correlativo"},
        ),
        migrations.AlterUniqueTogether(
            name="numerocorrelativo",
            unique_together={("id_empresa", "tipo")},
        ),
    ]
