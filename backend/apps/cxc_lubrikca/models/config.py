"""Modelos de configuración del motor (effective dating) — Fase 1.

Espejo Django de las dataclasses de configuración de ``cxc.models`` (sección 3.7+
de la especificación CxC Lubrikca). Reglas inviolables:

- **Dinero y porcentajes son ``Decimal``** (R-CODE-4), nunca ``float``. Los
  porcentajes se almacenan como FRACCIÓN (3 % → ``Decimal("0.03")``).
- **Multi-tenant** vía la FK ``empresa`` heredada de ``CxcLubrikcaBaseModel``
  (R-CODE-1).
- ``activo`` es la bandera de negocio del *effective dating* (distinta del
  *soft delete* ``deleted_at``): permite apagar una regla sin borrarla.
"""

from __future__ import annotations

from django.db import models

from .base import CxcLubrikcaBaseModel


# --- Enumerados (espejo de los Enum de cxc.models) --------------------------
class TipoDescuento(models.TextChoices):
    CONTADO = "contado", "Contado"


class Condicion(models.TextChoices):
    PRIMERA_COMPRA = "primera_compra", "Primera compra"
    RECOMPRA = "recompra", "Recompra"


class TipoBeneficio(models.TextChoices):
    NOTA_CREDITO = "nota_credito", "Nota de crédito"
    PORCENTAJE = "porcentaje", "Porcentaje"


class TipoFeriado(models.TextChoices):
    NACIONAL = "nacional", "Nacional"
    REGIONAL = "regional", "Regional"
    BANCARIO = "bancario", "Bancario"


class Moneda(models.TextChoices):
    USD = "USD", "USD"
    VES = "VES", "VES"


class TipoTasa(models.TextChoices):
    BCV = "BCV", "BCV"
    BINANCE = "Binance", "Binance"
    N_A = "N_A", "N/A"


# --- 3.7 DescuentosMarcaCategoria -------------------------------------------
class DescuentoMarcaCategoria(CxcLubrikcaBaseModel):
    """Descuento por marca/categoría con comodín ``*`` y effective dating."""

    marca = models.CharField(max_length=100, default="*")
    categoria = models.CharField(max_length=100, default="*")
    tipo_descuento = models.CharField(
        max_length=20, choices=TipoDescuento.choices, default=TipoDescuento.CONTADO
    )
    porcentaje = models.DecimalField(max_digits=9, decimal_places=6)
    vigencia_desde = models.DateField()
    vigencia_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-vigencia_desde"]
        verbose_name = "Descuento por marca/categoría"
        verbose_name_plural = "Descuentos por marca/categoría"

    def __str__(self) -> str:
        return f"{self.marca}/{self.categoria} — {self.porcentaje} (desde {self.vigencia_desde})"


# --- 3.7b DescuentoBCVCompleto ----------------------------------------------
class DescuentoBCVCompleto(CxcLubrikcaBaseModel):
    """Tasa de descuento BCV-completo que fija la gerencia (por fecha)."""

    porcentaje = models.DecimalField(max_digits=9, decimal_places=6)
    vigencia_desde = models.DateField()
    vigencia_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-vigencia_desde"]
        verbose_name = "Descuento BCV completo"
        verbose_name_plural = "Descuentos BCV completo"

    def __str__(self) -> str:
        return f"BCV-completo {self.porcentaje} (desde {self.vigencia_desde})"


# --- 3.7c PromocionPrimeraCompra --------------------------------------------
class PromocionPrimeraCompra(CxcLubrikcaBaseModel):
    """Producto de regalo por primera compra, con vigencia."""

    producto = models.CharField(max_length=200)
    vigencia_desde = models.DateField()
    vigencia_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-vigencia_desde"]
        verbose_name = "Promoción de primera compra"
        verbose_name_plural = "Promociones de primera compra"

    def __str__(self) -> str:
        return f"{self.producto} (desde {self.vigencia_desde})"


# --- 3.8 ReglasRecurrencia --------------------------------------------------
class ReglaRecurrencia(CxcLubrikcaBaseModel):
    """Beneficio por recurrencia (primera compra / recompra) con vigencia.

    ``valor`` guarda el monto para ``NOTA_CREDITO`` o la fracción para
    ``PORCENTAJE``.
    """

    condicion = models.CharField(max_length=20, choices=Condicion.choices)
    tipo_beneficio = models.CharField(max_length=20, choices=TipoBeneficio.choices)
    valor = models.DecimalField(max_digits=18, decimal_places=6)
    vigencia_desde = models.DateField()
    vigencia_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-vigencia_desde"]
        verbose_name = "Regla de recurrencia"
        verbose_name_plural = "Reglas de recurrencia"

    def __str__(self) -> str:
        return f"{self.condicion} → {self.tipo_beneficio} {self.valor} (desde {self.vigencia_desde})"


# --- 3.8b Feriados ----------------------------------------------------------
class Feriado(CxcLubrikcaBaseModel):
    """Feriado que extiende la ventana de contado (días hábiles)."""

    fecha = models.DateField()
    descripcion = models.CharField(max_length=200)
    tipo = models.CharField(
        max_length=20, choices=TipoFeriado.choices, default=TipoFeriado.NACIONAL
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["fecha"]
        unique_together = [["empresa", "fecha"]]
        verbose_name = "Feriado"
        verbose_name_plural = "Feriados"

    def __str__(self) -> str:
        return f"{self.fecha} — {self.descripcion}"


# --- 3.5 MetodosPago --------------------------------------------------------
class MetodoPago(CxcLubrikcaBaseModel):
    """Catálogo de métodos de pago (mapeo al journal_id de Odoo vía ``codigo``)."""

    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=120)
    moneda = models.CharField(max_length=3, choices=Moneda.choices)
    tipo_tasa = models.CharField(max_length=10, choices=TipoTasa.choices)
    es_contado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        unique_together = [["empresa", "codigo"]]
        verbose_name = "Método de pago"
        verbose_name_plural = "Métodos de pago"

    def __str__(self) -> str:
        return f"{self.codigo} — {self.nombre}"
