"""
M10-T5: Modelos SaaS — Plan y Suscripcion.

Plan:        Define los niveles de suscripción disponibles (FREE, STARTER, PRO, ENTERPRISE).
Suscripcion: Asocia una empresa a un plan con fechas de vigencia y estado.
"""

import uuid
from apps.core.uuid import uuid7

from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """
    Plan de suscripción SaaS.

    Define características, límites y precio de cada nivel de servicio.
    """

    NIVEL_CHOICES = [
        ("FREE", "Gratuito"),
        ("STARTER", "Starter"),
        ("PRO", "Pro"),
        ("ENTERPRISE", "Enterprise"),
    ]

    id_plan = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    nombre = models.CharField(max_length=50, unique=True)
    nivel = models.CharField(max_length=20, choices=NIVEL_CHOICES, default="FREE")
    descripcion = models.TextField(blank=True, default="")
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    precio_anual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_usuarios = models.PositiveIntegerField(
        default=5,
        help_text="Máximo de usuarios activos permitidos (0 = ilimitado).",
    )
    max_empresas = models.PositiveIntegerField(
        default=1,
        help_text="Máximo de empresas en la cuenta (0 = ilimitado).",
    )
    max_documentos_mes = models.PositiveIntegerField(
        default=100,
        help_text="Máximo de documentos (facturas/pedidos) por mes (0 = ilimitado).",
    )
    permite_ia = models.BooleanField(
        default=False,
        help_text="Acceso a módulos de Inteligencia Artificial (agentes M9).",
    )
    permite_api = models.BooleanField(
        default=False,
        help_text="Acceso a la API REST para integraciones.",
    )
    permite_reportes_avanzados = models.BooleanField(default=False)
    permite_multimoneda = models.BooleanField(default=False)
    soporte = models.CharField(
        max_length=30,
        choices=[
            ("email", "Email"),
            ("chat", "Chat"),
            ("telefono", "Teléfono"),
            ("dedicado", "Soporte Dedicado"),
        ],
        default="email",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saas_plan"
        verbose_name = "Plan"
        verbose_name_plural = "Planes"
        ordering = ["precio_mensual"]

    def __str__(self):
        return f"{self.nombre} ({self.nivel})"

    def es_ilimitado(self, campo: str) -> bool:
        """Verifica si un límite numérico es ilimitado (valor 0)."""
        return getattr(self, campo, 0) == 0


class Suscripcion(models.Model):
    """
    Suscripción de una empresa a un plan SaaS.

    Controla vigencia, estado y período de facturación.
    """

    ESTADO_CHOICES = [
        ("ACTIVA", "Activa"),
        ("VENCIDA", "Vencida"),
        ("CANCELADA", "Cancelada"),
        ("SUSPENDIDA", "Suspendida"),
        ("TRIAL", "Período de prueba"),
    ]

    PERIODO_CHOICES = [
        ("MENSUAL", "Mensual"),
        ("ANUAL", "Anual"),
    ]

    id_suscripcion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="suscripciones",
    )
    id_plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="suscripciones",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="TRIAL")
    periodo = models.CharField(max_length=10, choices=PERIODO_CHOICES, default="MENSUAL")
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    fecha_cancelacion = models.DateTimeField(null=True, blank=True)
    fecha_suspension = models.DateTimeField(null=True, blank=True)
    renovacion_automatica = models.BooleanField(default=True)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    referencia_pago = models.CharField(max_length=100, blank=True, default="")
    notas = models.TextField(blank=True, default="")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saas_suscripcion"
        verbose_name = "Suscripción"
        verbose_name_plural = "Suscripciones"
        ordering = ["-fecha_inicio"]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["fecha_fin", "estado"]),
        ]

    def __str__(self):
        return f"{self.id_empresa} → {self.id_plan} ({self.estado})"

    @property
    def esta_vigente(self) -> bool:
        """Retorna True si la suscripción está activa y dentro del período."""
        from datetime import date
        return (
            self.estado in ("ACTIVA", "TRIAL")
            and self.fecha_inicio <= date.today() <= self.fecha_fin
        )

    @property
    def dias_restantes(self) -> int:
        """Días hasta el vencimiento (puede ser negativo si ya venció)."""
        from datetime import date
        return (self.fecha_fin - date.today()).days

    def cancelar(self, notas: str = "") -> None:
        self.estado = "CANCELADA"
        self.fecha_cancelacion = timezone.now()
        if notas:
            self.notas = notas
        self.save(update_fields=["estado", "fecha_cancelacion", "notas"])

    def suspender(self) -> None:
        self.estado = "SUSPENDIDA"
        self.fecha_suspension = timezone.now()
        self.save(update_fields=["estado", "fecha_suspension"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def suscripcion_activa(empresa) -> "Suscripcion | None":
    """
    Retorna la suscripción vigente de una empresa, o None si no tiene.

    Args:
        empresa: instancia de Empresa.

    Returns:
        Suscripcion activa/trial más reciente, o None.
    """
    from datetime import date

    return (
        Suscripcion.objects.filter(
            id_empresa=empresa,
            estado__in=("ACTIVA", "TRIAL"),
            fecha_inicio__lte=date.today(),
            fecha_fin__gte=date.today(),
        )
        .select_related("id_plan")
        .order_by("-fecha_inicio")
        .first()
    )


def tiene_feature(empresa, feature: str) -> bool:
    """
    Verifica si la empresa tiene acceso a un feature específico del plan.

    Args:
        empresa: instancia de Empresa.
        feature: nombre del campo booleano en Plan (ej. "permite_ia").

    Returns:
        True si la suscripción está activa y el plan incluye el feature.
    """
    sus = suscripcion_activa(empresa)
    if sus is None:
        return False
    return bool(getattr(sus.id_plan, feature, False))
