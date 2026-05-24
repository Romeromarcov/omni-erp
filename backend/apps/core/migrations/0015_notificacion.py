"""
M10-T4: Add Notificacion model for in-app notifications.
"""
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_configuracion_flujo_documentos"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notificacion",
            fields=[
                ("id_notificacion", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("tipo", models.CharField(
                    choices=[
                        ("INFO", "Información"),
                        ("ALERTA", "Alerta"),
                        ("ADVERTENCIA", "Advertencia"),
                        ("ERROR", "Error"),
                        ("EXITO", "Éxito"),
                        ("COBRANZA", "Cobranza"),
                        ("INVENTARIO", "Inventario"),
                        ("SISTEMA", "Sistema"),
                    ],
                    default="INFO",
                    max_length=20,
                )),
                ("titulo", models.CharField(max_length=200)),
                ("mensaje", models.TextField()),
                ("leida", models.BooleanField(default=False, db_index=True)),
                ("fecha_lectura", models.DateTimeField(blank=True, null=True)),
                ("url_accion", models.CharField(blank=True, default="", max_length=500)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("fecha_expiracion", models.DateTimeField(blank=True, null=True)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notificaciones",
                        to="core.empresa",
                    ),
                ),
                (
                    "id_usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notificaciones",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Notificación",
                "verbose_name_plural": "Notificaciones",
                "db_table": "core_notificacion",
                "ordering": ["-fecha_creacion"],
                "indexes": [
                    models.Index(fields=["id_empresa", "id_usuario", "leida"], name="core_notif_empresa_usuario_leida_idx"),
                    models.Index(fields=["id_empresa", "tipo", "fecha_creacion"], name="core_notif_empresa_tipo_fecha_idx"),
                ],
            },
        ),
    ]
