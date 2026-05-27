"""
Integration Hub — Modelos
=========================
Permite a cada empresa (tenant) conectar Omni ERP con cualquier ERP o plataforma
externa. El primer conector funcional es Odoo (todas las versiones vía XML-RPC).

Arquitectura multi-tenant:
  - ConectorProveedor:  catálogo global (seed data) — no tiene id_empresa
  - ConectorInstancia:  una conexión configurada por empresa
  - EntidadSincronizada: mapa externo_id ↔ omni_id por empresa
  - JobSincronizacion:  ejecución de sincronización
  - LogDetalleSincronizacion: log por registro dentro de un job

Eventos emitidos:
  - integration_hub.conector_instancia.creada
  - integration_hub.conector_instancia.activada
  - integration_hub.job_sincronizacion.completado
  - integration_hub.job_sincronizacion.fallido
"""
import logging

from django.conf import settings
from django.db import models

from apps.core.uuid import uuid7

logger = logging.getLogger(__name__)


# ── Catálogo de proveedores (seed, sin id_empresa) ───────────────────────────

class ConectorProveedor(models.Model):
    """
    Tipo de integración soportada por el sistema (Odoo, SAP, etc.).
    Se puebla con fixtures; no es editable por los tenants.
    """
    ESTADO_CHOICES = [
        ("activo", "Activo"),
        ("beta", "Beta"),
        ("proximamente", "Próximamente"),
    ]

    id_proveedor = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    codigo = models.CharField(
        max_length=50, unique=True,
        help_text="Identificador slug del proveedor: odoo, sap_b1, shopify, etc.",
    )
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    icono_url = models.CharField(max_length=500, blank=True)
    versiones_soportadas = models.JSONField(
        default=list,
        help_text="['8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18']",
    )
    capacidades = models.JSONField(
        default=list,
        help_text=(
            "Lista de entidades soportadas: "
            "['contactos', 'productos', 'pedidos_venta', 'pedidos_compra', "
            "'facturas', 'pagos', 'inventario']"
        ),
    )
    requiere_url = models.BooleanField(default=True)
    requiere_db = models.BooleanField(default=False)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activo")
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Conector Proveedor"
        verbose_name_plural = "Conectores Proveedores"

    def __str__(self):
        return self.nombre


# ── Instancia de conector por empresa ────────────────────────────────────────

class ConectorInstancia(models.Model):
    """
    Conexión configurada entre una empresa y un sistema externo.

    Las credenciales se almacenan encriptadas en `configuracion`.
    El campo `configuracion` usa Django's encrypted fields si está disponible,
    de lo contrario se almacena como JSON (debe asegurarse TLS en BD).
    """
    ESTADO_CHOICES = [
        ("configurando", "Configurando"),
        ("activo", "Activo"),
        ("error", "Error de conexión"),
        ("inactivo", "Inactivo"),
    ]
    INTERVALO_CHOICES = [
        (0, "Solo manual"),
        (15, "Cada 15 minutos"),
        (30, "Cada 30 minutos"),
        (60, "Cada hora"),
        (360, "Cada 6 horas"),
        (720, "Cada 12 horas"),
        (1440, "Cada 24 horas"),
    ]

    id_conector = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="conectores",
        db_column="id_empresa",
    )
    id_proveedor = models.ForeignKey(
        ConectorProveedor,
        on_delete=models.PROTECT,
        related_name="instancias",
    )
    nombre = models.CharField(
        max_length=150,
        help_text='Nombre amigable, ej: "Odoo Producción"',
    )
    # Credenciales/config: {host, db, user, api_key, ...}
    # Nunca loguear este campo (R-CODE-8)
    configuracion = models.JSONField(
        default=dict,
        help_text="Credenciales y configuración de conexión (almacenadas encriptadas).",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="configurando")
    mensaje_estado = models.TextField(
        blank=True,
        help_text="Detalle del último error o resultado de test de conexión.",
    )
    ultimo_test_conexion = models.DateTimeField(null=True, blank=True)
    ultimo_sync = models.DateTimeField(null=True, blank=True)
    intervalo_sync_minutos = models.PositiveIntegerField(
        choices=INTERVALO_CHOICES,
        default=0,
        help_text="0 = solo sincronización manual.",
    )
    entidades_activas = models.JSONField(
        default=list,
        help_text="Entidades habilitadas para sync: ['contactos', 'productos', ...]",
    )
    version_detectada = models.CharField(
        max_length=50, blank=True,
        help_text="Versión del sistema externo detectada al hacer test de conexión.",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["id_empresa", "nombre"]]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["id_empresa", "activo"]),
        ]
        verbose_name = "Conector Instancia"
        verbose_name_plural = "Conectores Instancias"

    def __str__(self):
        return f"{self.nombre} ({self.id_empresa})"

    def get_config(self) -> dict:
        """Retorna la configuración. Nunca loguear el resultado (R-CODE-8)."""
        return self.configuracion or {}


# ── Mapa de entidades sincronizadas ──────────────────────────────────────────

class EntidadSincronizada(models.Model):
    """
    Registro del mapeo entre un ID externo y un ID en Omni ERP.
    Permite sincronización incremental y detección de conflictos.
    """
    TIPO_CHOICES = [
        ("contactos", "Contactos / Socios"),
        ("productos", "Productos"),
        ("pedidos_venta", "Pedidos de Venta"),
        ("pedidos_compra", "Pedidos de Compra"),
        ("facturas_venta", "Facturas de Venta"),
        ("facturas_compra", "Facturas de Compra"),
        ("pagos", "Pagos"),
        ("inventario", "Movimientos de Inventario"),
        ("empleados", "Empleados"),
    ]

    id_entidad_sync = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_instancia = models.ForeignKey(
        ConectorInstancia,
        on_delete=models.CASCADE,
        related_name="entidades_sincronizadas",
    )
    tipo_entidad = models.CharField(max_length=50, choices=TIPO_CHOICES)
    # ID tal como viene del sistema externo (puede ser int o str)
    id_externo = models.CharField(max_length=255)
    # UUID del registro en Omni (puede ser None si no se pudo crear)
    id_omni = models.CharField(max_length=255, null=True, blank=True)
    # nombre del modelo Django para facilitar lookup
    modelo_omni = models.CharField(
        max_length=150, blank=True,
        help_text="Ej: apps.ventas.models.Cliente",
    )
    ultimo_sync = models.DateTimeField(auto_now=True)
    # checksum del payload externo para detectar cambios sin re-comparar campo a campo
    checksum = models.CharField(max_length=64, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = [["id_instancia", "tipo_entidad", "id_externo"]]
        indexes = [
            models.Index(fields=["id_instancia", "tipo_entidad"]),
            models.Index(fields=["id_instancia", "id_omni"]),
        ]
        verbose_name = "Entidad Sincronizada"
        verbose_name_plural = "Entidades Sincronizadas"

    def __str__(self):
        return f"{self.tipo_entidad}:{self.id_externo} → {self.id_omni}"


# ── Job de sincronización ────────────────────────────────────────────────────

class JobSincronizacion(models.Model):
    """Representa una ejecución de sincronización (manual o automática)."""
    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("en_progreso", "En progreso"),
        ("completado", "Completado"),
        ("completado_con_errores", "Completado con errores"),
        ("fallido", "Fallido"),
        ("cancelado", "Cancelado"),
    ]
    DIRECCION_CHOICES = [
        ("inbound", "Externo → Omni"),
        ("outbound", "Omni → Externo"),
        ("bidireccional", "Bidireccional"),
    ]

    id_job = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_instancia = models.ForeignKey(
        ConectorInstancia,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    tipo_entidad = models.CharField(max_length=50)
    direccion = models.CharField(max_length=20, choices=DIRECCION_CHOICES, default="inbound")
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default="pendiente")
    # Contadores
    total_registros = models.PositiveIntegerField(default=0)
    procesados = models.PositiveIntegerField(default=0)
    creados = models.PositiveIntegerField(default=0)
    actualizados = models.PositiveIntegerField(default=0)
    omitidos = models.PositiveIntegerField(default=0)
    fallidos = models.PositiveIntegerField(default=0)
    # Resumen de errores (máx 50 para no inflar la BD)
    resumen_errores = models.JSONField(default=list)
    iniciado_en = models.DateTimeField(null=True, blank=True)
    completado_en = models.DateTimeField(null=True, blank=True)
    iniciado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="jobs_sincronizacion",
        help_text="Null = iniciado por tarea automática (Celery)",
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    # Parámetros del job (ej: {"desde": "2024-01-01", "limite": 100})
    parametros = models.JSONField(default=dict)

    class Meta:
        ordering = ["-iniciado_en"]
        indexes = [
            models.Index(fields=["id_instancia", "estado"]),
            models.Index(fields=["id_instancia", "tipo_entidad"]),
        ]
        verbose_name = "Job Sincronización"
        verbose_name_plural = "Jobs Sincronización"

    def __str__(self):
        return f"Job {self.tipo_entidad} [{self.estado}] — {self.id_instancia.nombre}"

    @property
    def duracion_segundos(self):
        if self.iniciado_en and self.completado_en:
            return (self.completado_en - self.iniciado_en).total_seconds()
        return None


# ── Log detallado por registro ───────────────────────────────────────────────

class LogDetalleSincronizacion(models.Model):
    """Log por registro individual dentro de un job de sincronización."""
    OPERACION_CHOICES = [
        ("crear", "Creado"),
        ("actualizar", "Actualizado"),
        ("omitir", "Omitido (sin cambios)"),
        ("error", "Error"),
        ("conflicto", "Conflicto"),
    ]

    id_log = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_job = models.ForeignKey(
        JobSincronizacion,
        on_delete=models.CASCADE,
        related_name="logs_detalle",
    )
    id_externo = models.CharField(max_length=255, blank=True)
    id_omni = models.CharField(max_length=255, blank=True)
    operacion = models.CharField(max_length=20, choices=OPERACION_CHOICES)
    # No almacenar datos completos de clientes/proveedores (R-CODE-8: sin datos sensibles)
    resumen_externo = models.JSONField(
        default=dict,
        help_text="Campos no sensibles del payload externo para debug.",
    )
    mensaje_error = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["id_job", "operacion"]),
        ]
        verbose_name = "Log Detalle Sincronización"
        verbose_name_plural = "Logs Detalle Sincronización"

    def __str__(self):
        return f"{self.operacion}: {self.id_externo} → {self.id_omni}"
