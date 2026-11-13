"""Administración de eventos de activación en puntos de venta.

Un *calendario* agrupa eventos y los *recursos* limitados (promotoras, igloos…) con su
capacidad simultánea. Un evento consume cantidades de esos recursos; la suma de lo usado
por eventos solapados nunca puede exceder la capacidad (ver ``services.verificar_capacidad``).
"""

from django.db import models
from django.db.models import F, Q

from apps.core.base_models import OmniBaseModel
from apps.core.uuid import uuid7


class CalendarioActivacion(OmniBaseModel):
    id_calendario = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="activaciones_calendarios",
    )
    nombre = models.CharField(max_length=100)
    # Id del calendario en Google Calendar; vacío = no se sincroniza.
    google_calendar_id = models.CharField(max_length=255, blank=True, default="")
    zona_horaria = models.CharField(max_length=50, default="America/Caracas")
    es_predeterminado = models.BooleanField(default=False)

    class Meta:
        db_table = "activaciones_calendario"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "nombre"],
                condition=Q(activo=True),
                name="activ_calendario_nombre_unico",
            ),
            models.UniqueConstraint(
                fields=["id_empresa"],
                condition=Q(es_predeterminado=True, activo=True),
                name="activ_calendario_un_predeterminado",
            ),
        ]

    def __str__(self):
        return self.nombre


class RecursoActivacion(OmniBaseModel):
    """Recurso limitado de un calendario (p. ej. ``promotoras`` = 2, ``igloos`` = 3)."""

    id_recurso = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="activaciones_recursos"
    )
    calendario = models.ForeignKey(
        CalendarioActivacion, on_delete=models.CASCADE, related_name="recursos"
    )
    codigo = models.SlugField(
        max_length=40, help_text="Identificador estable, p. ej. promotoras, igloos."
    )
    nombre = models.CharField(max_length=100)
    capacidad = models.PositiveSmallIntegerField(
        help_text="Unidades disponibles simultáneamente."
    )

    class Meta:
        db_table = "activaciones_recurso"
        ordering = ["calendario", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["calendario", "codigo"],
                condition=Q(activo=True),
                name="activ_recurso_codigo_unico",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.capacidad})"


class EventoActivacion(OmniBaseModel):
    class Estado(models.TextChoices):
        PROGRAMADO = "PROGRAMADO", "Programado"
        REALIZADO = "REALIZADO", "Realizado"
        CANCELADO = "CANCELADO", "Cancelado"

    class Origen(models.TextChoices):
        WEB = "WEB", "Web"
        BOT = "BOT", "Bot de Telegram"

    id_evento = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="activaciones_eventos"
    )
    calendario = models.ForeignKey(
        CalendarioActivacion, on_delete=models.PROTECT, related_name="eventos"
    )
    cliente = models.ForeignKey(
        "crm.Cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activaciones",
    )
    cliente_nombre = models.CharField(
        max_length=255, help_text="Nombre tal como lo indicó el vendedor."
    )
    vendedor = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activaciones",
    )
    vendedor_nombre = models.CharField(max_length=150, blank=True, default="")
    ubicacion = models.CharField(
        max_length=500, help_text="Punto de venta / dirección."
    )
    inicio = models.DateTimeField()
    fin = models.DateTimeField()
    materiales = models.JSONField(
        default=list, blank=True, help_text="Lista de materiales a llevar."
    )
    notas = models.TextField(blank=True, default="")
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PROGRAMADO
    )
    origen = models.CharField(max_length=4, choices=Origen.choices, default=Origen.WEB)
    google_event_id = models.CharField(max_length=255, blank=True, default="")
    sync_error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "activaciones_evento"
        ordering = ["inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fin__gt=F("inicio")), name="activ_evento_fin_gt_inicio"
            )
        ]
        indexes = [models.Index(fields=["calendario", "estado", "inicio", "fin"])]

    def __str__(self):
        return f"{self.cliente_nombre} · {self.inicio:%Y-%m-%d %H:%M}"


class UsoRecursoEvento(OmniBaseModel):
    id_uso = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="activaciones_usos"
    )
    evento = models.ForeignKey(
        EventoActivacion, on_delete=models.CASCADE, related_name="usos"
    )
    recurso = models.ForeignKey(
        RecursoActivacion, on_delete=models.PROTECT, related_name="usos"
    )
    cantidad = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "activaciones_uso_recurso"
        constraints = [
            models.UniqueConstraint(
                fields=["evento", "recurso"], name="activ_uso_unico"
            ),
            models.CheckConstraint(
                condition=Q(cantidad__gt=0), name="activ_uso_cantidad_positiva"
            ),
        ]
