import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0002_delete_pagocontribucionparafiscal"),
        ("core", "0010_base_model_empresa_sucursal_departamento"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConfiguracionFiscalEmpresa",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "id_empresa",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configuracion_fiscal",
                        to="core.empresa",
                    ),
                ),
                ("contribuyente_iva", models.BooleanField(default=True)),
                ("aplica_igtf", models.BooleanField(default=True)),
                ("tasa_igtf", models.DecimalField(decimal_places=4, default="0.03", max_digits=5)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "fiscal_configuracion_empresa"},
        ),
        migrations.CreateModel(
            name="TasaIVAEmpresa",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tasas_iva",
                        to="core.empresa",
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("GENERAL", "General"),
                            ("REDUCIDO", "Reducido"),
                            ("EXENTO", "Exento"),
                            ("ADICIONAL", "Adicional"),
                        ],
                        max_length=10,
                    ),
                ),
                ("nombre", models.CharField(max_length=50)),
                ("tasa", models.DecimalField(decimal_places=6, max_digits=7)),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "fiscal_tasa_iva_empresa"},
        ),
        migrations.AlterUniqueTogether(
            name="tasaivaempresa",
            unique_together={("id_empresa", "tipo")},
        ),
    ]
