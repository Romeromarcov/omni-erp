"""
Modelos de Gestión de Cobranza.

GestionCobranza: registro de una acción de cobranza (llamada, WhatsApp, etc.)
PlantillaCobranza: mensajes reutilizables con variables interpolables.
"""
from django.db import models

from .base import CxcBaseModel


class PlantillaCobranza(CxcBaseModel):
    """
    Mensaje de cobranza reutilizable con variables.
    Variables soportadas: {cliente} {orden} {monto} {vencimiento} {dias_vencida}
    """
    nombre = models.CharField(max_length=100)
    canal = models.CharField(
        max_length=20,
        choices=[
            ("whatsapp", "WhatsApp"),
            ("email", "Email"),
            ("sms", "SMS"),
            ("carta", "Carta"),
            ("llamada", "Guión Llamada"),
        ],
    )
    asunto = models.CharField(max_length=200, blank=True)
    cuerpo = models.TextField(help_text="Variables: {cliente} {orden} {monto} {vencimiento} {dias_vencida}")
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Plantilla de Cobranza"
        verbose_name_plural = "Plantillas de Cobranza"
        indexes = [
            models.Index(fields=["empresa", "canal", "activa"]),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.canal})"

    def renderizar(self, contexto: dict) -> str:
        """
        Renderiza el cuerpo con variables del contexto.
        contexto: {cliente, orden, monto, vencimiento, dias_vencida}
        """
        try:
            return self.cuerpo.format(**contexto)
        except KeyError:
            return self.cuerpo  # Retorna sin reemplazar si falta variable


class GestionCobranza(CxcBaseModel):
    """
    Registro de una acción de cobranza sobre un cliente/cuenta.

    cliente_id: referencia flexible — puede ser id de CRM Omni (Mode B)
                o id_externo de Odoo (Mode A).
    cxc: FK opcional al CuentaPorCobrar nativo (solo Mode B).
    """

    CANAL_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("llamada", "Llamada"),
        ("visita", "Visita"),
        ("carta", "Carta"),
    ]

    RESULTADO_CHOICES = [
        ("contactado", "Contactado"),
        ("sin_respuesta", "Sin Respuesta"),
        ("promesa_pago", "Promesa de Pago"),
        ("negativa", "Negativa"),
        ("acuerdo_logrado", "Acuerdo Logrado"),
    ]

    # Referencia al cliente (flexible: Omni o externo)
    cliente_id = models.CharField(
        max_length=100,
        help_text="ID del cliente (UUID Omni en Mode B, ID externo Odoo en Mode A)",
    )
    cliente_nombre = models.CharField(max_length=255, blank=True)
    orden_ref = models.CharField(max_length=100, blank=True, help_text="Referencia de la orden/factura")

    # FK opcional al CxC nativo (Mode B)
    cxc = models.ForeignKey(
        "cuentas_por_cobrar.CuentaPorCobrar",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones_cobranza",
    )

    # Acción
    canal = models.CharField(max_length=20, choices=CANAL_CHOICES)
    resultado = models.CharField(max_length=30, choices=RESULTADO_CHOICES)
    notas = models.TextField(blank=True)
    plantilla = models.ForeignKey(
        PlantillaCobranza,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones",
    )

    # Score calculado al guardar
    score = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    # Seguimiento
    fecha_gestion = models.DateField()
    proxima_accion = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de próximo contacto (aplica cuando resultado=promesa_pago)",
    )

    # Actor
    gestionado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones_cobranza",
    )

    class Meta:
        verbose_name = "Gestión de Cobranza"
        verbose_name_plural = "Gestiones de Cobranza"
        ordering = ["-fecha_gestion"]
        indexes = [
            models.Index(fields=["empresa", "cliente_id"]),
            models.Index(fields=["empresa", "proxima_accion"]),
            models.Index(fields=["empresa", "resultado", "fecha_gestion"]),
        ]

    def __str__(self):
        return f"{self.cliente_nombre} — {self.canal} — {self.resultado} ({self.fecha_gestion})"
