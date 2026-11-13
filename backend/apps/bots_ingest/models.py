"""Ingesta de borradores confirmados desde los bots de Telegram.

Los bots (pedidos/CRM, cobranza, pagos a proveedores, eventos) autentican con un usuario de servicio
(JWT) que tenga el permiso ``bots_ingest.ingestar`` y envían ``telegram_user_id`` en ``fuente``; ese id
se resuelve a un vendedor/empresa vía ``BotUsuario``. Toda ingesta queda registrada (auditoría +
idempotencia por ``idempotency_key``).
"""

from django.db import models
from django.db.models import Q

from apps.core.base_models import OmniBaseModel
from apps.core.uuid import uuid7


class BotUsuario(OmniBaseModel):
    """Vincula un usuario de Telegram con un usuario Omni (vendedor) de una empresa."""

    id_bot_usuario = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="bots_usuarios"
    )
    telegram_user_id = models.BigIntegerField()
    usuario = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, related_name="bots_usuarios"
    )
    nombre = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "bots_ingest_usuario"
        constraints = [
            # Un usuario de Telegram pertenece a una sola empresa activa.
            models.UniqueConstraint(
                fields=["telegram_user_id"],
                condition=Q(activo=True),
                name="bots_usuario_telegram_unico",
            ),
        ]

    def __str__(self):
        return f"{self.telegram_user_id} → {self.usuario}"


class IngestaBot(OmniBaseModel):
    class Kind(models.TextChoices):
        CONTACTO = "contacto", "Contacto (CRM)"
        COTIZACION = "cotizacion", "Cotización"
        PEDIDO = "pedido", "Pedido"
        PAGO = "pago", "Pago de cliente"
        PAGO_PROVEEDOR = "pago_proveedor", "Pago a proveedor"
        EVENTO = "evento", "Evento de activación"

    class Estado(models.TextChoices):
        PROCESADO = "PROCESADO", "Procesado"
        BORRADOR = "BORRADOR", "Borrador completo (por confirmar en Odoo)"
        INCOMPLETO = "INCOMPLETO", "Incompleto (faltan datos)"
        SINCRONIZADO = "SINCRONIZADO", "Sincronizado con Odoo"
        ERROR = "ERROR", "Error"

    id_ingesta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="bots_ingestas"
    )
    bot_usuario = models.ForeignKey(
        BotUsuario, on_delete=models.PROTECT, related_name="ingestas"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    idempotency_key = models.CharField(max_length=120)
    payload = models.JSONField(help_text="Borrador tal como lo confirmó el usuario.")
    fuente = models.JSONField(default=dict, help_text="chat_id, message_id, bot, auto…")
    auto = models.BooleanField(
        default=False, help_text="Enviado automáticamente por falta de respuesta."
    )
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PROCESADO
    )
    incompleto = models.JSONField(
        default=list, blank=True, help_text="Campos/datos que faltan."
    )
    resultado = models.JSONField(
        default=dict, blank=True, help_text="Referencias a lo creado en Omni."
    )
    odoo_ref = models.CharField(max_length=100, blank=True, default="")
    error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "bots_ingest_ingesta"
        ordering = ["-fecha_creacion"]
        permissions = [("ingestar", "Puede enviar borradores desde los bots")]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "idempotency_key"], name="bots_ingesta_idem_unica"
            ),
        ]
        indexes = [models.Index(fields=["id_empresa", "estado", "kind"])]

    def __str__(self):
        return f"{self.kind} {self.estado} {self.idempotency_key}"
