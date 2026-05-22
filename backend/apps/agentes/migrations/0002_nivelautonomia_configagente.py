"""
0002_nivelautonomia_configagente.py

Agrega NivelAutonomia (TextChoices) y el modelo ConfigAgente para controlar
el nivel de autonomía de cada agente por empresa (Sprint 0.F).
"""

import apps.core.uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agentes", "0001_initial"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConfigAgente",
            fields=[
                (
                    "id_config",
                    models.UUIDField(
                        default=apps.core.uuid.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "agente",
                    models.CharField(
                        choices=[
                            ("clasificador_gastos", "Clasificador de Gastos"),
                            ("cobranza_estratega", "Estratega de Cobranza"),
                            ("reorden_sugeridor", "Sugeridor de Reorden"),
                            ("personalizacion_capa2", "Personalización Capa 2"),
                        ],
                        db_index=True,
                        max_length=50,
                    ),
                ),
                (
                    "nivel_autonomia",
                    models.CharField(
                        choices=[
                            ("SOMBRA", "Sombra (solo observa)"),
                            ("SUGERENCIA", "Sugerencia (requiere aprobación humana)"),
                            ("AUTONOMO", "Autónomo (ejecuta sin intervención)"),
                        ],
                        default="SOMBRA",
                        max_length=20,
                    ),
                ),
                (
                    "umbral_confianza_minimo",
                    models.FloatField(
                        default=0.8,
                        help_text="Confianza mínima (0.0–1.0) para que el agente actúe automáticamente.",
                    ),
                ),
                ("activo", models.BooleanField(default=True)),
                (
                    "max_acciones_por_dia",
                    models.IntegerField(
                        default=100,
                        help_text="Límite de acciones autónomas por día (solo aplica si nivel=AUTONOMO).",
                    ),
                ),
                ("config_extra", models.JSONField(blank=True, default=dict)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configs_agentes",
                        to="core.empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "Configuración de Agente",
                "verbose_name_plural": "Configuraciones de Agentes",
                "db_table": "agentes_config_agente",
                "unique_together": {("id_empresa", "agente")},
            },
        ),
    ]
