import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas_por_pagar", "0002_delete_pagocxp"),
        ("core", "0012_contacto"),
    ]

    operations = [
        migrations.CreateModel(
            name="AbonoCxP",
            fields=[
                (
                    "id_abono_cxp",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "monto",
                    models.DecimalField(decimal_places=4, max_digits=18),
                ),
                ("fecha_abono", models.DateField(auto_now_add=True)),
                ("descripcion", models.TextField(blank=True, default="")),
                (
                    "referencia_externa",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                (
                    "cuenta_por_pagar",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="abonos",
                        to="cuentas_por_pagar.cuentaporpagar",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="core.usuarios",
                    ),
                ),
            ],
            options={
                "db_table": "cuentas_por_pagar_abono_cxp",
            },
        ),
    ]
