"""
Modelos de Acuerdos de Pago.

AcuerdoPago: acuerdo de pago en cuotas con un cliente.
CuotaAcuerdo: cuota individual del acuerdo, linkeable a finanzas.Pago.
"""
from apps.core.uuid import uuid7
from django.db import models

from .base import CxcBaseModel


class AcuerdoPago(CxcBaseModel):
    """Acuerdo de pago formalizado con un cliente."""

    PERIODICIDAD_CHOICES = [
        ("unico", "Pago Único"),
        ("semanal", "Semanal"),
        ("quincenal", "Quincenal"),
        ("mensual", "Mensual"),
    ]

    ESTADO_CHOICES = [
        ("vigente", "Vigente"),
        ("cumplido", "Cumplido"),
        ("roto", "Roto"),
        ("cancelado", "Cancelado"),
    ]

    # Referencia al cliente
    cliente_id = models.CharField(max_length=100)
    cliente_nombre = models.CharField(max_length=255, blank=True)

    # FK opcional a CxC nativo
    cxc = models.ForeignKey(
        "cuentas_por_cobrar.CuentaPorCobrar",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acuerdos_pago",
    )

    # Gestión origen
    gestion = models.ForeignKey(
        "cxc.GestionCobranza",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acuerdos",
    )

    # Estructura del acuerdo
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)
    periodicidad = models.CharField(max_length=20, choices=PERIODICIDAD_CHOICES)
    plazo_total_dias = models.PositiveIntegerField(default=30)
    fecha_inicio = models.DateField()

    # Monto de cuota (uno de los dos, no ambos)
    monto_cuota = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    porcentaje_abono = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Porcentaje del total a pagar por cuota (0-100)"
    )

    # Estado
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="vigente")

    # Moneda de referencia
    moneda_codigo = models.CharField(max_length=5, default="USD", help_text="Código ISO de moneda (USD, VES, etc.)")

    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Acuerdo de Pago"
        verbose_name_plural = "Acuerdos de Pago"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["empresa", "cliente_id", "estado"]),
            models.Index(fields=["empresa", "estado"]),
        ]

    def __str__(self):
        return f"Acuerdo {self.cliente_nombre} — {self.monto_total} {self.moneda_codigo} ({self.estado})"


class CuotaAcuerdo(models.Model):
    """Cuota individual de un acuerdo de pago."""

    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("pagado", "Pagado"),
        ("parcial", "Parcial"),
        ("vencido", "Vencido"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    acuerdo = models.ForeignKey(
        AcuerdoPago,
        on_delete=models.CASCADE,
        related_name="cuotas",
    )
    numero_cuota = models.PositiveSmallIntegerField()
    fecha_vencimiento = models.DateField()
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="pendiente")

    # Pago efectivo (va en finanzas.Pago — no modelo propio)
    pago = models.ForeignKey(
        "finanzas.Pago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cuotas_acuerdo",
    )
    monto_pagado = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    fecha_pago = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cuota de Acuerdo"
        verbose_name_plural = "Cuotas de Acuerdo"
        ordering = ["numero_cuota"]
        indexes = [
            models.Index(fields=["acuerdo", "fecha_vencimiento", "estado"]),
        ]

    def __str__(self):
        return f"Cuota {self.numero_cuota} — {self.monto} — {self.estado}"
