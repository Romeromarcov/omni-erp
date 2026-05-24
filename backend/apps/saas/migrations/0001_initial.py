"""
M10-T5: Initial migration for SaaS Plan and Suscripcion models.
"""
import django.db.models.deletion
import uuid
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0015_notificacion"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id_plan", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("nombre", models.CharField(max_length=50, unique=True)),
                ("nivel", models.CharField(
                    choices=[
                        ("FREE", "Gratuito"),
                        ("STARTER", "Starter"),
                        ("PRO", "Pro"),
                        ("ENTERPRISE", "Enterprise"),
                    ],
                    default="FREE",
                    max_length=20,
                )),
                ("descripcion", models.TextField(blank=True, default="")),
                ("precio_mensual", models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ("precio_anual", models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ("max_usuarios", models.PositiveIntegerField(default=5)),
                ("max_empresas", models.PositiveIntegerField(default=1)),
                ("max_documentos_mes", models.PositiveIntegerField(default=100)),
                ("permite_ia", models.BooleanField(default=False)),
                ("permite_api", models.BooleanField(default=False)),
                ("permite_reportes_avanzados", models.BooleanField(default=False)),
                ("permite_multimoneda", models.BooleanField(default=False)),
                ("soporte", models.CharField(
                    choices=[
                        ("email", "Email"),
                        ("chat", "Chat"),
                        ("telefono", "Teléfono"),
                        ("dedicado", "Soporte Dedicado"),
                    ],
                    default="email",
                    max_length=30,
                )),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Plan",
                "verbose_name_plural": "Planes",
                "db_table": "saas_plan",
                "ordering": ["precio_mensual"],
            },
        ),
        migrations.CreateModel(
            name="Suscripcion",
            fields=[
                ("id_suscripcion", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("estado", models.CharField(
                    choices=[
                        ("ACTIVA", "Activa"),
                        ("VENCIDA", "Vencida"),
                        ("CANCELADA", "Cancelada"),
                        ("SUSPENDIDA", "Suspendida"),
                        ("TRIAL", "Período de prueba"),
                    ],
                    default="TRIAL",
                    max_length=20,
                )),
                ("periodo", models.CharField(
                    choices=[("MENSUAL", "Mensual"), ("ANUAL", "Anual")],
                    default="MENSUAL",
                    max_length=10,
                )),
                ("fecha_inicio", models.DateField()),
                ("fecha_fin", models.DateField()),
                ("fecha_cancelacion", models.DateTimeField(blank=True, null=True)),
                ("fecha_suspension", models.DateTimeField(blank=True, null=True)),
                ("renovacion_automatica", models.BooleanField(default=True)),
                ("monto_pagado", models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ("referencia_pago", models.CharField(blank=True, default="", max_length=100)),
                ("notas", models.TextField(blank=True, default="")),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="suscripciones",
                        to="core.empresa",
                    ),
                ),
                (
                    "id_plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="suscripciones",
                        to="saas.plan",
                    ),
                ),
            ],
            options={
                "verbose_name": "Suscripción",
                "verbose_name_plural": "Suscripciones",
                "db_table": "saas_suscripcion",
                "ordering": ["-fecha_inicio"],
                "indexes": [
                    models.Index(fields=["id_empresa", "estado"], name="saas_sus_empresa_estado_idx"),
                    models.Index(fields=["fecha_fin", "estado"], name="saas_sus_fin_estado_idx"),
                ],
            },
        ),
    ]
