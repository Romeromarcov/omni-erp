import uuid

from django.db import models


class PrediccionAgente(models.Model):
    """
    Registro inmutable de cada predicción emitida por un agente en shadow mode.
    Nunca modifica datos de negocio; solo observa y predice.
    """

    AGENTE_CHOICES = [
        ("clasificador_gastos", "Clasificador de Gastos"),
    ]
    RESULTADO_CHOICES = [
        ("aceptada", "Aceptada por humano"),
        ("rechazada", "Rechazada por humano"),
        ("pendiente", "Pendiente revisión"),
    ]

    id_prediccion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
