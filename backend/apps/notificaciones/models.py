from django.db import models

from apps.core.uuid import uuid7


class CanalNotificacion(models.TextChoices):
    IN_APP = "IN_APP", "En aplicación"
    EMAIL = "EMAIL", "Correo electrónico"


class PlantillaNotificacion(models.Model):
    """Template reutilizable para generar el contenido de una notificación."""

    id_plantilla = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    codigo_plantilla = models.CharField(max_length=50, unique=True, db_index=True)
    asunto = models.CharField(max_length=200)
    cuerpo_html = models.TextField()
    canal = models.CharField(max_length=10, choices=CanalNotificacion.choices)
    variables_json = models.JSONField(
        default=list,
        blank=True,
        help_text='Lista de variables requeridas, ej: ["nombre_cliente", "numero_pedido"]',
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notificaciones_plantilla"
        verbose_name = "Plantilla de Notificación"
        verbose_name_plural = "Plantillas de Notificaciones"
        ordering = ["codigo_plantilla"]

    def __str__(self):
        return f"{self.codigo_plantilla} [{self.canal}]"


class EventoNotificacion(models.Model):
    """Define qué eventos generan notificaciones, configurado por empresa."""

    id_evento = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    codigo_evento = models.CharField(max_length=50, db_index=True)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="eventos_notificacion",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificaciones_evento"
        verbose_name = "Evento de Notificación"
        verbose_name_plural = "Eventos de Notificación"
        unique_together = [["codigo_evento", "id_empresa"]]

    def __str__(self):
        return f"{self.codigo_evento} @ {self.id_empresa_id}"


class SuscripcionNotificacion(models.Model):
    """Suscripción de un usuario a un evento por un canal específico."""

    id_suscripcion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_evento = models.ForeignKey(
        EventoNotificacion,
        on_delete=models.CASCADE,
        related_name="suscripciones",
    )
    id_usuario = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.CASCADE,
        related_name="suscripciones_notificacion",
    )
    canal = models.CharField(max_length=10, choices=CanalNotificacion.choices)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "notificaciones_suscripcion"
        verbose_name = "Suscripción de Notificación"
        verbose_name_plural = "Suscripciones de Notificaciones"
        unique_together = [["id_evento", "id_usuario", "canal"]]

    def __str__(self):
        return f"{self.id_evento} → {self.id_usuario_id} [{self.canal}]"


class LogNotificacion(models.Model):
    """Registro de intentos de entrega de notificaciones (especialmente email)."""

    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("ENVIADO", "Enviado"),
        ("FALLIDO", "Fallido"),
    ]

    id_log = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_plantilla = models.ForeignKey(
        PlantillaNotificacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    destinatario = models.CharField(
        max_length=200,
        help_text="Email o user_id del destinatario",
    )
    canal = models.CharField(max_length=10, choices=CanalNotificacion.choices)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="PENDIENTE")
    intentos = models.IntegerField(default=0)
    error = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notificaciones_log"
        verbose_name = "Log de Notificación"
        verbose_name_plural = "Logs de Notificaciones"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.canal}→{self.destinatario} [{self.estado}]"
