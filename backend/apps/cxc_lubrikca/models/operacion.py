"""Modelos de operación del motor CxC Lubrikca — Fase 3.

Capa de datos PERSISTIDA del motor determinístico. En Fase 5 el espejo
(``PedidoLubrikca``, ``LineaPedidoLubrikca``, ``PrecioListaLubrikca``,
``PagoLubrikca``) se poblará desde Odoo; por ahora es escribible/seedeable.

La EXTENSIÓN propia del subproyecto (nunca se sincroniza desde Odoo) son
``Vinculacion`` (pago↔pedido con equivalentes congelados) y
``BandejaFacturacion`` (salida del motor + cierre híbrido). NO se toca
``AbonoCxC`` del núcleo.

Reglas inviolables:
- Dinero y tasas son ``Decimal`` (R-CODE-4), nunca ``float``.
- Multi-tenant vía la FK ``empresa`` de ``CxcLubrikcaBaseModel`` (R-CODE-1).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from .base import CxcLubrikcaBaseModel
from .config import Moneda, TipoTasa


# --- 3.11 ResultadoConciliacion (semáforo motor-vs-factura) -----------------
class ResultadoConciliacion(models.TextChoices):
    VERDE = "verde", "Verde (cuadra)"
    AMARILLO = "amarillo", "Amarillo (revisar)"
    ROJO = "rojo", "Rojo (se facturó distinto)"


# --- Enumerados propios de operación ---------------------------------------
class EstadoEntrega(models.TextChoices):
    PENDING = "pending", "Pendiente"
    PARTIAL = "partial", "Parcial"
    FULL = "full", "Completa"


class EstadoVinculacion(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    APROBADO = "aprobado", "Aprobado"
    FACTURADO = "facturado", "Facturado"
    CONCILIADO = "conciliado", "Conciliado"


class EstadoBandeja(models.TextChoices):
    CALCULADO = "calculado", "Calculado"
    APROBADO = "aprobado", "Aprobado"
    FACTURADO = "facturado", "Facturado"


# --- 3.2 PedidoLubrikca (espejo de OrdenVenta) ------------------------------
class PedidoLubrikca(CxcLubrikcaBaseModel):
    """Espejo de la orden de venta (Odoo SO). Fase 5 lo sincroniza."""

    so_id = models.CharField(max_length=100)
    cliente_externo_id = models.CharField(max_length=100)
    cliente_nombre = models.CharField(max_length=200, blank=True)
    vendedor_email = models.CharField(max_length=254, blank=True)
    fecha = models.DateField()
    fecha_entrega = models.DateField(null=True, blank=True)
    monto_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    lista_precios = models.CharField(max_length=50)
    es_primera_compra = models.BooleanField(default=False)
    facturada = models.BooleanField(default=False)
    factura_id = models.CharField(max_length=100, blank=True)
    monto_facturado = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    # Notas de crédito reales de Odoo (out_refund). Fase 5 las poblará.
    ncs_facturadas = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )
    estado_entrega = models.CharField(
        max_length=20, choices=EstadoEntrega.choices, blank=True
    )
    entregada_completa = models.BooleanField(default=False)
    tiene_devolucion = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha"]
        unique_together = [["empresa", "so_id"]]
        verbose_name = "Pedido (espejo)"
        verbose_name_plural = "Pedidos (espejo)"

    def __str__(self) -> str:
        return f"SO {self.so_id} ({self.fecha})"


# --- 3.3 LineaPedidoLubrikca (espejo de LineaOrden) -------------------------
class LineaPedidoLubrikca(CxcLubrikcaBaseModel):
    pedido = models.ForeignKey(
        PedidoLubrikca, on_delete=models.CASCADE, related_name="lineas"
    )
    linea_id = models.CharField(max_length=100)
    producto = models.CharField(max_length=200)
    marca = models.CharField(max_length=100, default="*")
    categoria = models.CharField(max_length=100, default="*")
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    cantidad_entregada = models.DecimalField(
        max_digits=18, decimal_places=4, default=0
    )

    class Meta:
        ordering = ["linea_id"]
        verbose_name = "Línea de pedido (espejo)"
        verbose_name_plural = "Líneas de pedido (espejo)"

    def __str__(self) -> str:
        return f"{self.producto} x{self.cantidad}"


# --- PrecioListaLubrikca (fuente del price resolver) ------------------------
class PrecioListaLubrikca(CxcLubrikcaBaseModel):
    """Precio de un producto en una lista (USD/BCV). Fase 5 lo llena desde Odoo."""

    producto = models.CharField(max_length=200)
    lista = models.CharField(max_length=50)
    precio = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        ordering = ["producto", "lista"]
        unique_together = [["empresa", "producto", "lista"]]
        verbose_name = "Precio de lista"
        verbose_name_plural = "Precios de lista"

    def __str__(self) -> str:
        return f"{self.producto}@{self.lista} = {self.precio}"


# --- 3.4 PagoLubrikca (espejo de Pago) --------------------------------------
class PagoLubrikca(CxcLubrikcaBaseModel):
    pago_id = models.CharField(max_length=100)
    cliente_externo_id = models.CharField(max_length=100)
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    moneda = models.CharField(max_length=3, choices=Moneda.choices)
    metodo_pago = models.CharField(max_length=50)
    fecha_pago = models.DateTimeField()
    vendedor_email = models.CharField(max_length=254, blank=True)
    vinculado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha_pago"]
        unique_together = [["empresa", "pago_id"]]
        verbose_name = "Pago (espejo)"
        verbose_name_plural = "Pagos (espejo)"

    def __str__(self) -> str:
        return f"Pago {self.pago_id} {self.monto} {self.moneda}"


# --- 3.9 Vinculacion (pago↔pedido + equivalentes congelados; EXTENSIÓN) -----
class Vinculacion(CxcLubrikcaBaseModel):
    """Vinculación pago↔pedido con tasas estampadas y equivalentes congelados.

    Es trabajo humano: el sync de Odoo NUNCA la toca. No confundir con
    ``AbonoCxC`` del núcleo: esta es la extensión específica de Lubrikca.
    """

    pedido = models.ForeignKey(
        PedidoLubrikca, on_delete=models.CASCADE, related_name="vinculaciones"
    )
    pago = models.ForeignKey(
        PagoLubrikca, on_delete=models.CASCADE, related_name="vinculaciones"
    )
    monto_aplicado = models.DecimalField(max_digits=18, decimal_places=4)
    hora_pago_confirmada = models.DateTimeField()
    tasa_bcv_aplicada = models.DecimalField(max_digits=18, decimal_places=8)
    tasa_binance_aplicada = models.DecimalField(max_digits=18, decimal_places=8)
    es_tasa_heredada = models.BooleanField(default=False)
    moneda_abono = models.CharField(max_length=3, choices=Moneda.choices)
    tipo_tasa_abono = models.CharField(
        max_length=10, choices=TipoTasa.choices, default=TipoTasa.N_A
    )
    # Equivalentes congelados (3.9b) — calculados UNA vez, nunca recalculados.
    equiv_usd_bcv = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    equiv_usd_binance = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    equiv_ves_bcv = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    equiv_ves_binance = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    estado = models.CharField(
        max_length=20,
        choices=EstadoVinculacion.choices,
        default=EstadoVinculacion.PENDIENTE,
    )
    confirmado_por = models.ForeignKey(
        "core.Usuarios", null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Vinculación pago↔pedido"
        verbose_name_plural = "Vinculaciones pago↔pedido"

    def __str__(self) -> str:
        return f"Vinc {self.monto_aplicado} ({self.moneda_abono})"


# --- 3.10 BandejaFacturacion (salida del motor + cierre híbrido) ------------
class BandejaFacturacion(CxcLubrikcaBaseModel):
    pedido = models.OneToOneField(
        PedidoLubrikca, on_delete=models.CASCADE, related_name="bandeja"
    )
    lista_aplicada = models.CharField(max_length=50)
    precio_base_calculado = models.DecimalField(max_digits=18, decimal_places=2)
    descuentos_detalle = models.JSONField(default=list)
    total_descuentos = models.DecimalField(
        max_digits=18, decimal_places=2, default=0
    )
    ncs_calculadas = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_motor = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    requiere_revision = models.BooleanField(default=False)
    candidata_a_cierre = models.BooleanField(default=False)
    estado = models.CharField(
        max_length=20, choices=EstadoBandeja.choices, default=EstadoBandeja.CALCULADO
    )
    aprobado_por = models.ForeignKey(
        "core.Usuarios", null=True, blank=True, on_delete=models.SET_NULL
    )
    calculado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-calculado_en"]
        verbose_name = "Bandeja de facturación"
        verbose_name_plural = "Bandejas de facturación"

    def __str__(self) -> str:
        return f"Bandeja {self.pedido.so_id} — {self.total_motor}"


# --- Fase 4: Conciliación (semáforo motor-vs-factura) -----------------------
class ConfiguracionConciliacion(CxcLubrikcaBaseModel):
    """Tolerancias del semáforo de conciliación por empresa.

    El servicio usa get-or-create con defaults; se ordena por ``-created_at``
    para que la fila más reciente sea la activa (no hay unique por empresa para
    permitir historial editable vía CRUD).
    """

    tolerance_rounding = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.01")
    )
    tolerance_red = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("1.00")
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Configuración de conciliación"
        verbose_name_plural = "Configuraciones de conciliación"

    def __str__(self) -> str:
        return f"Tolerancias ±{self.tolerance_rounding}/±{self.tolerance_red}"


class ConciliacionLubrikca(CxcLubrikcaBaseModel):
    """Resultado del semáforo motor-vs-factura para un pedido facturado.

    El motor dice lo que la factura DEBERÍA ser (``total_motor``); Odoo dice lo
    que FUE (``monto_facturado`` − ``ncs``). La diferencia se clasifica con el
    semáforo verde/amarillo/rojo. Write-back purista: nada se escribe a Odoo.
    """

    pedido = models.OneToOneField(
        PedidoLubrikca, on_delete=models.CASCADE, related_name="conciliacion"
    )
    total_motor = models.DecimalField(max_digits=18, decimal_places=2)
    monto_facturado = models.DecimalField(max_digits=18, decimal_places=2)
    ncs = models.DecimalField(max_digits=18, decimal_places=2)
    diferencia = models.DecimalField(max_digits=18, decimal_places=2)
    resultado = models.CharField(
        max_length=10, choices=ResultadoConciliacion.choices
    )
    revisado_por = models.ForeignKey(
        "core.Usuarios", null=True, blank=True, on_delete=models.SET_NULL
    )
    conciliado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-conciliado_en"]
        verbose_name = "Conciliación"
        verbose_name_plural = "Conciliaciones"

    def __str__(self) -> str:
        return f"Conciliación {self.pedido.so_id} — {self.resultado}"
