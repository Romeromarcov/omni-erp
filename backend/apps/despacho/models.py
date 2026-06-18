"""
Modelos de despacho/entrega (sub-fase 1.G del Plan Maestro).

Decisiones de diseño (ver README.md de la app):

- El despacho documenta la **logística de entrega** de una venta: quién la
  transporta, a dónde, cuándo salió y cuándo se entregó (o devolvió). **NO toca
  inventario**: el stock físico ya salió con el movimiento ``DESPACHO_VENTA``
  que genera ``apps.ventas.services.entregar_nota_venta()`` al confirmar la
  venta. Crear/entregar/devolver un Despacho nunca crea MovimientoInventario.
- Origen: la "venta confirmada" del flujo es la **NotaVenta** en estado
  ``ENTREGADA`` o ``FACTURADA`` (estados posteriores a la salida de stock).
  ``id_pedido`` se conserva como referencia informativa del documento raíz.
  Se eliminó ``id_orden_compra``: la entrada de mercancía de compras la cubre
  ``RecepcionMercancia`` (apps/compras); un despacho es siempre saliente.
- Despacho **parcial por líneas**: ``DetalleDespacho`` (la "LineaDespacho" del
  plan; se mantiene el nombre por consistencia con DetallePedido /
  DetalleNotaVenta y con la tabla ya existente) permite repartir una venta en
  varios viajes. La suma despachada por producto (en despachos PENDIENTE /
  EN_RUTA / ENTREGADO) nunca puede exceder lo vendido en la nota.
- Estados y transiciones (timestamps por transición):
    PENDIENTE → EN_RUTA   (fecha_en_ruta)      → ENTREGADO (fecha_entrega_real)
    PENDIENTE → CANCELADO (fecha_cancelacion)
    EN_RUTA   → DEVUELTO  (fecha_devolucion)
  ENTREGADO / DEVUELTO / CANCELADO son terminales. CANCELADO y DEVUELTO liberan
  el cupo despachable de la nota (la mercancía no llegó al cliente).
- Firma y receptor de la entrega se registran en ``documento_json["entrega"]``
  (IntegrationFieldsMixin), no como columnas: es evidencia documental, no
  lógica de negocio.
"""

from django.db import models

from apps.core.base_models import IntegrationFieldsMixin, TenantModel
from apps.core.uuid import uuid7


class Despacho(TenantModel, IntegrationFieldsMixin):
    """Encabezado del despacho: la entrega física de una venta al cliente."""

    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_EN_RUTA = "EN_RUTA"
    ESTADO_ENTREGADO = "ENTREGADO"
    ESTADO_DEVUELTO = "DEVUELTO"
    ESTADO_CANCELADO = "CANCELADO"

    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_EN_RUTA, "En ruta"),
        (ESTADO_ENTREGADO, "Entregado"),
        (ESTADO_DEVUELTO, "Devuelto"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    # Máquina de estados: estado actual → estados alcanzables.
    TRANSICIONES = {
        ESTADO_PENDIENTE: frozenset({ESTADO_EN_RUTA, ESTADO_CANCELADO}),
        ESTADO_EN_RUTA: frozenset({ESTADO_ENTREGADO, ESTADO_DEVUELTO}),
        ESTADO_ENTREGADO: frozenset(),
        ESTADO_DEVUELTO: frozenset(),
        ESTADO_CANCELADO: frozenset(),
    }

    # Estados cuyos detalles consumen el cupo despachable de la nota de venta
    # (CANCELADO y DEVUELTO lo liberan: la mercancía no quedó en el cliente).
    ESTADOS_CONSUMEN_CUPO = (ESTADO_PENDIENTE, ESTADO_EN_RUTA, ESTADO_ENTREGADO)

    id_despacho = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="despachos"
    )
    # Correlativo por empresa (fiscal.NumeroCorrelativo tipo=DESPACHO).
    numero_despacho = models.CharField(max_length=50)
    # Venta origen: nota de venta ya ENTREGADA/FACTURADA (el stock ya salió).
    # PROTECT: un despacho histórico no debe quedar huérfano de su venta.
    id_nota_venta = models.ForeignKey(
        "ventas.NotaVenta",
        on_delete=models.PROTECT,
        related_name="despachos",
        null=True,
        blank=True,
        help_text="Nota de venta origen (ENTREGADA/FACTURADA). Nulo solo en despachos manuales.",
    )
    # Referencia informativa al pedido raíz del flujo (si existió).
    id_pedido = models.ForeignKey(
        "ventas.Pedido",
        on_delete=models.SET_NULL,
        related_name="despachos",
        null=True,
        blank=True,
    )
    fecha_despacho = models.DateTimeField(help_text="Fecha del documento de despacho.")
    id_almacen_origen = models.ForeignKey(
        "almacenes.Almacen", on_delete=models.PROTECT, related_name="despachos_origen"
    )
    direccion_destino = models.TextField(
        verbose_name="Dirección de entrega",
        help_text="Dirección física donde se entrega la mercancía.",
    )
    # Transportista/chofer opcional (empleado de la misma empresa).
    id_transportista = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="despachos_transportista",
    )
    estado_despacho = models.CharField(
        max_length=20, choices=ESTADOS, default=ESTADO_PENDIENTE
    )
    fecha_entrega_estimada = models.DateTimeField(null=True, blank=True)
    # Timestamps por transición de estado.
    fecha_en_ruta = models.DateTimeField(null=True, blank=True)
    fecha_entrega_real = models.DateTimeField(null=True, blank=True)
    fecha_devolucion = models.DateTimeField(null=True, blank=True)
    fecha_cancelacion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "despacho_despacho"
        verbose_name = "Despacho"
        verbose_name_plural = "Despachos"
        ordering = ["-fecha_despacho", "-fecha_creacion"]
        # Multi-tenant: el correlativo es por empresa, no global.
        unique_together = [["id_empresa", "numero_despacho"]]
        indexes = [
            models.Index(fields=["id_empresa", "estado_despacho"]),
            models.Index(fields=["fecha_despacho"]),
        ]

    def __str__(self):
        return f"{self.numero_despacho} - {self.estado_despacho}"

    def puede_transicionar_a(self, nuevo_estado: str) -> bool:
        """True si la máquina de estados permite pasar al estado dado."""
        return nuevo_estado in self.TRANSICIONES.get(self.estado_despacho, frozenset())


class DetalleDespacho(models.Model):
    """
    Línea de despacho ("LineaDespacho" del plan): producto y cantidad que viaja
    en este despacho. Permite el despacho parcial de una venta en varios viajes.

    Las líneas se crean vía ``services.crear_despacho_desde_nota_venta`` (que
    valida el cupo contra la venta); por API son de solo lectura.
    """

    id_detalle_despacho = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_despacho = models.ForeignKey(
        "Despacho", on_delete=models.CASCADE, related_name="detalles"
    )
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.PROTECT, related_name="detalles_despacho"
    )
    cantidad_despachada = models.DecimalField(max_digits=18, decimal_places=4)
    id_unidad_medida = models.ForeignKey(
        "inventario.UnidadMedida", on_delete=models.PROTECT, related_name="detalles_despacho"
    )
    lote = models.CharField(max_length=50, null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "despacho_detalle_despacho"
        verbose_name = "Detalle de Despacho"
        verbose_name_plural = "Detalles de Despacho"

    def __str__(self):
        return (
            f"{self.id_despacho.numero_despacho} - "
            f"{self.id_producto.nombre_producto} x {self.cantidad_despachada}"
        )
