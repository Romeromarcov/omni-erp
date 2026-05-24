import uuid
from apps.core.uuid import uuid7

from django.db import models


class NivelAutonomia(models.TextChoices):
    """
    Niveles de autonomía de un agente (R-PROC-8).

    SOMBRA     — Solo observa y registra predicciones. No ejecuta ninguna acción.
    SUGERENCIA — Propone acciones al usuario; el humano aprueba antes de ejecutar.
    AUTONOMO   — Ejecuta acciones sin aprobación humana dentro de los límites configurados.
    """

    SOMBRA = "SOMBRA", "Sombra (solo observa)"
    SUGERENCIA = "SUGERENCIA", "Sugerencia (requiere aprobación humana)"
    AUTONOMO = "AUTONOMO", "Autónomo (ejecuta sin intervención)"


class ConfigAgente(models.Model):
    """
    Configuración por empresa de un agente específico.

    Permite al superadmin o al tenant controlar el nivel de autonomía,
    los umbrales de confianza y si el agente está activo para esa empresa.
    """

    id_config = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="configs_agentes",
        db_index=True,
    )
    agente = models.CharField(
        max_length=50,
        choices=[
            ("clasificador_gastos", "Clasificador de Gastos"),
            ("cobranza_estratega", "Estratega de Cobranza"),
            ("reorden_sugeridor", "Sugeridor de Reorden"),
            ("personalizacion_capa2", "Personalización Capa 2"),
        ],
        db_index=True,
    )
    nivel_autonomia = models.CharField(
        max_length=20,
        choices=NivelAutonomia.choices,
        default=NivelAutonomia.SOMBRA,
    )
    umbral_confianza_minimo = models.FloatField(
        default=0.80,
        help_text="Confianza mínima (0.0–1.0) para que el agente actúe automáticamente.",
    )
    activo = models.BooleanField(default=True)
    max_acciones_por_dia = models.IntegerField(
        default=100,
        help_text="Límite de acciones autónomas por día (solo aplica si nivel=AUTONOMO).",
    )
    config_extra = models.JSONField(default=dict, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agentes_config_agente"
        verbose_name = "Configuración de Agente"
        verbose_name_plural = "Configuraciones de Agentes"
        unique_together = [["id_empresa", "agente"]]

    def __str__(self) -> str:
        return f"{self.agente} @ {self.id_empresa_id} [{self.nivel_autonomia}]"


class PrediccionAgente(models.Model):
    """
    Registro inmutable de cada predicción emitida por un agente en shadow mode.
    Nunca modifica datos de negocio; solo observa y predice.
    """

    AGENTE_CHOICES = [
        ("clasificador_gastos", "Clasificador de Gastos"),
        ("cobranza_estratega", "Estratega de Cobranza"),
        ("reorden_sugeridor", "Sugeridor de Reorden"),
        ("personalizacion_capa2", "Personalización Capa 2"),
    ]
    RESULTADO_CHOICES = [
        ("aceptada", "Aceptada por humano"),
        ("rechazada", "Rechazada por humano"),
        ("pendiente", "Pendiente revisión"),
    ]

    id_prediccion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, db_index=True)
    agente = models.CharField(max_length=50, choices=AGENTE_CHOICES, db_index=True)

    # Entrada
    input_texto = models.TextField()
    input_monto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    input_metadata = models.JSONField(default=dict, blank=True)

    # Salida
    categoria_predicha = models.CharField(max_length=100)
    confianza = models.FloatField()  # 0.0 – 1.0
    razonamiento = models.TextField(blank=True)
    alternativas = models.JSONField(default=list, blank=True)

    # Evaluación humana
    resultado_humano = models.CharField(
        max_length=20, choices=RESULTADO_CHOICES, default="pendiente"
    )
    categoria_correcta = models.CharField(max_length=100, blank=True)

    # Metadatos
    modelo_llm = models.CharField(max_length=100, default="fallback")
    latencia_ms = models.IntegerField(default=0)
    fecha_prediccion = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["id_empresa", "agente", "fecha_prediccion"]),
            models.Index(fields=["agente", "resultado_humano"]),
        ]
        ordering = ["-fecha_prediccion"]

    def __str__(self):
        return f"{self.agente}:{self.categoria_predicha}({self.confianza:.0%})"
