"""Migration: PeriodoFiscal — cierre de períodos fiscales por empresa."""
import apps.core.uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0004_numero_correlativo"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PeriodoFiscal",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="periodos_fiscales",
                        to="core.empresa",
                    ),
                ),
                ("año", models.PositiveSmallIntegerField()),
                ("mes", models.PositiveSmallIntegerField()),
                ("cerrado", models.BooleanField(default=False)),
                ("fecha_cierre", models.DateTimeField(blank=True, null=True)),
                (
                    "cerrado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.usuarios",
                    ),
                ),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "fiscal_periodo_fiscal",
                "unique_together": {("id_empresa", "año", "mes")},
            },
        ),
    ]
