"""
Fraccionamiento de productos (feature-flagged).

Solo activo si get_config('cxc.fraccionamiento.enabled') == 'true'.
"""
from decimal import Decimal

from django.db import models

from .base import CxcBaseModel


class LoteFraccionado(CxcBaseModel):
    """
    Lote de producto que se vende fraccionado (ej: vender por gramo/unidad
    desde un lote mayor comprado por kg/caja).
    """
    producto_id = models.CharField(max_length=100, help_text="ID del producto (Omni o externo Odoo)")
    producto_nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)

    # Cantidades
    cantidad_inicial = models.DecimalField(max_digits=14, decimal_places=4)
    cantidad_actual = models.DecimalField(max_digits=14, decimal_places=4)

    # Unidades
    unidad_base = models.CharField(max_length=20, help_text="Unidad de compra (kg, caja, etc.)")
    unidad_venta = models.CharField(max_length=20, help_text="Unidad de venta (g, unidad, etc.)")
    factor_conversion = models.DecimalField(
        max_digits=14, decimal_places=6,
        help_text="Cuántas unidades_venta hay en 1 unidad_base"
    )

    precio_venta_unit = models.DecimalField(max_digits=18, decimal_places=4)
    moneda_codigo = models.CharField(max_length=5, default="USD")

    estado = models.CharField(
        max_length=20,
        choices=[("activo", "Activo"), ("agotado", "Agotado"), ("cerrado", "Cerrado")],
        default="activo",
    )

    class Meta:
        verbose_name = "Lote Fraccionado"
        verbose_name_plural = "Lotes Fraccionados"
        indexes = [
            models.Index(fields=["empresa", "estado"]),
        ]

    def __str__(self):
        return f"{self.producto_nombre} ({self.cantidad_actual} {self.unidad_venta})"


class VentaFraccionada(CxcBaseModel):
    """
    Venta de una fracción de un lote.
    El pago va a finanzas.Pago (no modelo propio).
    """
    lote = models.ForeignKey(
        LoteFraccionado,
        on_delete=models.PROTECT,
        related_name="ventas",
    )
    cliente_id = models.CharField(max_length=100)
    cliente_nombre = models.CharField(max_length=255, blank=True)

    cantidad = models.DecimalField(max_digits=14, decimal_places=4)
    precio_unit = models.DecimalField(max_digits=18, decimal_places=4)
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)
    moneda_codigo = models.CharField(max_length=5, default="USD")

    estado = models.CharField(
        max_length=20,
        choices=[
            ("pendiente", "Pendiente"),
            ("confirmada", "Confirmada"),
            ("anulada", "Anulada"),
        ],
        default="pendiente",
    )

    # Pago va en finanzas.Pago
    pago = models.ForeignKey(
        "finanzas.Pago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas_fraccionadas",
    )

    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = "Venta Fraccionada"
        verbose_name_plural = "Ventas Fraccionadas"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Venta {self.cantidad} {self.lote.unidad_venta} de {self.lote.producto_nombre}"
