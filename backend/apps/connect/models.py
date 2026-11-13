"""Omni Connect — perfil digital, tarjeta NFC y eventos de toque (S1).

Todas las tablas son multi-tenant (``id_empresa``) y están protegidas por RLS
(ver ``migrations/0002_rls_connect.py`` y ``apps.core.rls.RLS_TABLES``).

El perfil es público (se resuelve por slug sin login); esa lectura pública se
implementa en S2 en contexto de sistema y solo expone campos del propio perfil.
"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.base_models import OmniBaseModel
from apps.core.uuid import uuid7

from .validators import (
    normalizar_uid_chip,
    validar_misma_empresa,
    validar_slug_perfil,
    validar_uid_chip,
)


class Perfil(OmniBaseModel):
    """Perfil digital público de un usuario del tenant (``omni.link/<slug>``)."""

    id_perfil = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="connect_perfiles"
    )
    usuario = models.ForeignKey(
        "core.Usuarios", on_delete=models.PROTECT, related_name="connect_perfiles"
    )
    # Global (no por empresa): la URL pública corta no lleva tenant.
    slug = models.CharField(max_length=60, unique=True, validators=[validar_slug_perfil])
    nombre_publico = models.CharField(max_length=150)
    cargo = models.CharField(max_length=150, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    telefono_publico = models.CharField(max_length=50, blank=True, default="")
    email_publico = models.EmailField(blank=True, default="")
    tema = models.CharField(max_length=30, default="CLASICO")
    # [{"tipo": "whatsapp", "etiqueta": "...", "valor": "..."}]; se valida en S2.
    botones = models.JSONField(default=list, blank=True)
    # En cuentas Equipo, el admin bloquea la plantilla corporativa.
    plantilla_bloqueada = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Perfil Connect"
        verbose_name_plural = "Perfiles Connect"
        ordering = ["nombre_publico"]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "usuario"], name="connect_perfil_unico_por_usuario"
            ),
        ]
        indexes = [models.Index(fields=["id_empresa", "activo"])]

    def __str__(self):
        return f"{self.nombre_publico} ({self.slug})"

    def clean(self):
        super().clean()
        if self.usuario_id and not self.usuario.empresas.filter(
            pk=self.id_empresa_id
        ).exists():
            raise ValidationError({"usuario": "El usuario no pertenece a esta empresa."})


class Tarjeta(OmniBaseModel):
    """Tarjeta o pulsera NFC física, identificada por el UID de su chip."""

    class Tipo(models.TextChoices):
        PVC = "PVC", "PVC"
        METAL = "METAL", "Metal"
        PULSERA = "PULSERA", "Pulsera"

    class Estado(models.TextChoices):
        INVENTARIO = "INVENTARIO", "En inventario (sin asignar)"
        ACTIVA = "ACTIVA", "Activa"
        DESACTIVADA = "DESACTIVADA", "Desactivada"
        PERDIDA = "PERDIDA", "Perdida"

    id_tarjeta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="connect_tarjetas"
    )
    # Una tarjeta en inventario aún no tiene perfil; se puede reasignar después.
    perfil = models.ForeignKey(
        Perfil,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tarjetas",
    )
    # Global: el UID es físico y único; evita que dos tenants reclamen el mismo chip.
    uid_chip = models.CharField(max_length=20, unique=True, validators=[validar_uid_chip])
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.PVC)
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.INVENTARIO
    )
    fecha_activacion = models.DateTimeField(null=True, blank=True)
    notas = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Tarjeta Connect"
        verbose_name_plural = "Tarjetas Connect"
        ordering = ["-fecha_creacion"]
        constraints = [
            # Una tarjeta ACTIVA siempre apunta a un perfil.
            models.CheckConstraint(
                condition=~models.Q(estado="ACTIVA") | models.Q(perfil__isnull=False),
                name="connect_tarjeta_activa_con_perfil",
            ),
        ]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["id_empresa", "perfil"]),
        ]

    def __str__(self):
        return f"{self.tipo} {self.uid_chip} [{self.estado}]"

    def save(self, *args, **kwargs):
        self.uid_chip = normalizar_uid_chip(self.uid_chip)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.uid_chip = normalizar_uid_chip(self.uid_chip)
        validar_misma_empresa(self, perfil=self.perfil)


class Toque(OmniBaseModel):
    """Toque NFC, escaneo de QR o visita directa a un perfil (analíticas)."""

    class Origen(models.TextChoices):
        NFC = "NFC", "Toque NFC"
        QR = "QR", "Código QR"
        ENLACE = "ENLACE", "Enlace directo"

    class Dispositivo(models.TextChoices):
        IOS = "IOS", "iPhone / iPad"
        ANDROID = "ANDROID", "Android"
        ESCRITORIO = "ESCRITORIO", "Escritorio"
        OTRO = "OTRO", "Otro / desconocido"

    id_toque = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="connect_toques"
    )
    perfil = models.ForeignKey(Perfil, on_delete=models.PROTECT, related_name="toques")
    # Nulo cuando la visita no viene de una tarjeta (QR o enlace).
    tarjeta = models.ForeignKey(
        Tarjeta, on_delete=models.PROTECT, null=True, blank=True, related_name="toques"
    )
    origen = models.CharField(max_length=10, choices=Origen.choices, default=Origen.NFC)
    dispositivo = models.CharField(
        max_length=12, choices=Dispositivo.choices, default=Dispositivo.OTRO
    )
    fecha_toque = models.DateTimeField(auto_now_add=True, db_index=True)
    # Privacidad: nunca se guarda la IP en claro, solo un hash salado (anti-spam/únicos).
    ip_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "Toque Connect"
        verbose_name_plural = "Toques Connect"
        ordering = ["-fecha_toque"]
        indexes = [
            models.Index(fields=["id_empresa", "fecha_toque"]),
            models.Index(fields=["id_empresa", "perfil", "fecha_toque"]),
        ]

    def __str__(self):
        return f"{self.origen} → {self.perfil_id} @ {self.fecha_toque:%Y-%m-%d %H:%M}"

    def clean(self):
        super().clean()
        validar_misma_empresa(self, perfil=self.perfil, tarjeta=self.tarjeta)
