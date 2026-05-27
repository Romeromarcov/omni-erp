"""
Migration inicial del Integration Hub.
Generada manualmente — ejecutar: python manage.py migrate integration_hub
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import apps.core.uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── ConectorProveedor ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="ConectorProveedor",
            fields=[
                ("id_proveedor", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("codigo", models.CharField(help_text="Identificador slug del proveedor: odoo, sap_b1, shopify, etc.", max_length=50, unique=True)),
                ("nombre", models.CharField(max_length=100)),
                ("descripcion", models.TextField(blank=True)),
                ("icono_url", models.CharField(blank=True, max_length=500)),
                ("versiones_soportadas", models.JSONField(default=list)),
                ("capacidades", models.JSONField(default=list)),
                ("requiere_url", models.BooleanField(default=True)),
                ("requiere_db", models.BooleanField(default=False)),
                ("estado", models.CharField(choices=[("activo", "Activo"), ("beta", "Beta"), ("proximamente", "Próximamente")], default="activo", max_length=20)),
                ("activo", models.BooleanField(default=True)),
                ("orden", models.PositiveSmallIntegerField(default=100)),
            ],
            options={"ordering": ["orden", "nombre"], "verbose_name": "Conector Proveedor", "verbose_name_plural": "Conectores Proveedores"},
        ),

        # ── ConectorInstancia ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="ConectorInstancia",
            fields=[
                ("id_conector", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("id_empresa", models.ForeignKey(db_column="id_empresa", on_delete=django.db.models.deletion.CASCADE, related_name="conectores", to="core.empresa")),
                ("id_proveedor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="instancias", to="integration_hub.conectorproveedor")),
                ("nombre", models.CharField(help_text='Nombre amigable, ej: "Odoo Producción"', max_length=150)),
                ("configuracion", models.JSONField(default=dict)),
                ("estado", models.CharField(choices=[("configurando", "Configurando"), ("activo", "Activo"), ("error", "Error de conexión"), ("inactivo", "Inactivo")], default="configurando", max_length=20)),
                ("mensaje_estado", models.TextField(blank=True)),
                ("ultimo_test_conexion", models.DateTimeField(blank=True, null=True)),
                ("ultimo_sync", models.DateTimeField(blank=True, null=True)),
                ("intervalo_sync_minutos", models.PositiveIntegerField(choices=[(0, "Solo manual"), (15, "Cada 15 minutos"), (30, "Cada 30 minutos"), (60, "Cada hora"), (360, "Cada 6 horas"), (720, "Cada 12 horas"), (1440, "Cada 24 horas")], default=0)),
                ("entidades_activas", models.JSONField(default=list)),
                ("version_detectada", models.CharField(blank=True, max_length=50)),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Conector Instancia", "verbose_name_plural": "Conectores Instancias"},
        ),
        migrations.AddConstraint(
            model_name="conectorinstancia",
            constraint=models.UniqueConstraint(fields=["id_empresa", "nombre"], name="unique_instancia_por_empresa"),
        ),
        migrations.AddIndex(
            model_name="conectorinstancia",
            index=models.Index(fields=["id_empresa", "estado"], name="ih_instancia_empresa_estado_idx"),
        ),
        migrations.AddIndex(
            model_name="conectorinstancia",
            index=models.Index(fields=["id_empresa", "activo"], name="ih_instancia_empresa_activo_idx"),
        ),

        # ── EntidadSincronizada ────────────────────────────────────────────────
        migrations.CreateModel(
            name="EntidadSincronizada",
            fields=[
                ("id_entidad_sync", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("id_instancia", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entidades_sincronizadas", to="integration_hub.conectorinstancia")),
                ("tipo_entidad", models.CharField(choices=[("contactos", "Contactos / Socios"), ("productos", "Productos"), ("pedidos_venta", "Pedidos de Venta"), ("pedidos_compra", "Pedidos de Compra"), ("facturas_venta", "Facturas de Venta"), ("facturas_compra", "Facturas de Compra"), ("pagos", "Pagos"), ("inventario", "Movimientos de Inventario"), ("empleados", "Empleados")], max_length=50)),
                ("id_externo", models.CharField(max_length=255)),
                ("id_omni", models.CharField(blank=True, max_length=255, null=True)),
                ("modelo_omni", models.CharField(blank=True, max_length=150)),
                ("ultimo_sync", models.DateTimeField(auto_now=True)),
                ("checksum", models.CharField(blank=True, max_length=64)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "Entidad Sincronizada", "verbose_name_plural": "Entidades Sincronizadas"},
        ),
        migrations.AddConstraint(
            model_name="entidadsincronizada",
            constraint=models.UniqueConstraint(fields=["id_instancia", "tipo_entidad", "id_externo"], name="unique_entidad_sync"),
        ),
        migrations.AddIndex(
            model_name="entidadsincronizada",
            index=models.Index(fields=["id_instancia", "tipo_entidad"], name="ih_entidad_instancia_tipo_idx"),
        ),
        migrations.AddIndex(
            model_name="entidadsincronizada",
            index=models.Index(fields=["id_instancia", "id_omni"], name="ih_entidad_instancia_omni_idx"),
        ),

        # ── JobSincronizacion ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="JobSincronizacion",
            fields=[
                ("id_job", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("id_instancia", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jobs", to="integration_hub.conectorinstancia")),
                ("tipo_entidad", models.CharField(max_length=50)),
                ("direccion", models.CharField(choices=[("inbound", "Externo → Omni"), ("outbound", "Omni → Externo"), ("bidireccional", "Bidireccional")], default="inbound", max_length=20)),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente"), ("en_progreso", "En progreso"), ("completado", "Completado"), ("completado_con_errores", "Completado con errores"), ("fallido", "Fallido"), ("cancelado", "Cancelado")], default="pendiente", max_length=30)),
                ("total_registros", models.PositiveIntegerField(default=0)),
                ("procesados", models.PositiveIntegerField(default=0)),
                ("creados", models.PositiveIntegerField(default=0)),
                ("actualizados", models.PositiveIntegerField(default=0)),
                ("omitidos", models.PositiveIntegerField(default=0)),
                ("fallidos", models.PositiveIntegerField(default=0)),
                ("resumen_errores", models.JSONField(default=list)),
                ("iniciado_en", models.DateTimeField(blank=True, null=True)),
                ("completado_en", models.DateTimeField(blank=True, null=True)),
                ("iniciado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="jobs_sincronizacion", to=settings.AUTH_USER_MODEL)),
                ("celery_task_id", models.CharField(blank=True, max_length=255)),
                ("parametros", models.JSONField(default=dict)),
            ],
            options={"ordering": ["-iniciado_en"], "verbose_name": "Job Sincronización", "verbose_name_plural": "Jobs Sincronización"},
        ),
        migrations.AddIndex(
            model_name="jobsincronizacion",
            index=models.Index(fields=["id_instancia", "estado"], name="ih_job_instancia_estado_idx"),
        ),
        migrations.AddIndex(
            model_name="jobsincronizacion",
            index=models.Index(fields=["id_instancia", "tipo_entidad"], name="ih_job_instancia_tipo_idx"),
        ),

        # ── LogDetalleSincronizacion ───────────────────────────────────────────
        migrations.CreateModel(
            name="LogDetalleSincronizacion",
            fields=[
                ("id_log", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("id_job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="logs_detalle", to="integration_hub.jobsincronizacion")),
                ("id_externo", models.CharField(blank=True, max_length=255)),
                ("id_omni", models.CharField(blank=True, max_length=255)),
                ("operacion", models.CharField(choices=[("crear", "Creado"), ("actualizar", "Actualizado"), ("omitir", "Omitido (sin cambios)"), ("error", "Error"), ("conflicto", "Conflicto")], max_length=20)),
                ("resumen_externo", models.JSONField(default=dict)),
                ("mensaje_error", models.TextField(blank=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-creado_en"], "verbose_name": "Log Detalle Sincronización", "verbose_name_plural": "Logs Detalle Sincronización"},
        ),
        migrations.AddIndex(
            model_name="logdetallesincronizacion",
            index=models.Index(fields=["id_job", "operacion"], name="ih_log_job_operacion_idx"),
        ),
    ]
