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

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.base_models import IntegrationFieldsMixin, OmniBaseModel, TenantModel
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
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="despachos")
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
    estado_despacho = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_PENDIENTE)
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
    id_despacho = models.ForeignKey("Despacho", on_delete=models.CASCADE, related_name="detalles")
    id_producto = models.ForeignKey("inventario.Producto", on_delete=models.PROTECT, related_name="detalles_despacho")
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
            f"{self.id_despacho.numero_despacho} - " f"{self.id_producto.nombre_producto} x {self.cantidad_despachada}"
        )


# ── Modelos Logística TMS Inteligente (Plan 09 Fase 6) ────────────────────────


class ZonaLogistica(OmniBaseModel):
    """Zona geográfica de despacho con centroide y tarifa base de flete."""

    id_zona = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="zonas_logisticas")
    codigo = models.CharField(max_length=30)
    nombre = models.CharField(max_length=120)
    ciudad = models.CharField(max_length=100, blank=True, default="")
    estado_provincia = models.CharField(max_length=100, blank=True, default="")
    centro_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    centro_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radio_km = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("15.00"))
    tarifa_base_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    tiempo_servicio_min = models.PositiveIntegerField(default=15)
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "despacho_zona_logistica"
        verbose_name = "Zona Logística"
        verbose_name_plural = "Zonas Logísticas"
        unique_together = [["id_empresa", "codigo"]]
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(condition=Q(radio_km__gte=0), name="desp_zona_radio_gte_0"),
            models.CheckConstraint(condition=Q(tarifa_base_usd__gte=0), name="desp_zona_tarifa_gte_0"),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class TarifaFlete(OmniBaseModel):
    """Regla de cálculo de flete por zona logística (FIJA, KG, KM, M3, PALETA)."""

    TIPOS_CALCULO = [
        ("FIJA", "Tarifa Fija por Viaje"),
        ("POR_KG", "Por Kilogramo"),
        ("POR_KM", "Por Kilómetro"),
        ("POR_M3", "Por Metro Cúbico"),
        ("POR_PALETA", "Por Paleta"),
    ]

    id_tarifa = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="tarifas_flete")
    id_zona = models.ForeignKey(ZonaLogistica, on_delete=models.CASCADE, related_name="tarifas_flete")
    tipo_calculo = models.CharField(max_length=20, choices=TIPOS_CALCULO, default="FIJA")
    monto_base_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    tarifa_unidad_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    minimo_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    moneda_referencia = models.CharField(max_length=10, default="USD")

    class Meta:
        db_table = "despacho_tarifa_flete"
        verbose_name = "Tarifa de Flete"
        verbose_name_plural = "Tarifas de Flete"
        constraints = [
            models.CheckConstraint(condition=Q(monto_base_usd__gte=0), name="desp_tarifa_base_gte_0"),
            models.CheckConstraint(condition=Q(tarifa_unidad_usd__gte=0), name="desp_tarifa_unit_gte_0"),
            models.CheckConstraint(condition=Q(minimo_usd__gte=0), name="desp_tarifa_min_gte_0"),
        ]

    def clean(self):
        super().clean()
        if self.id_zona_id and self.id_empresa_id and self.id_zona.id_empresa_id != self.id_empresa_id:
            raise ValidationError({"id_zona": "La zona logística no pertenece a la empresa indicada."})

    def __str__(self):
        return f"{self.id_zona.nombre} ({self.tipo_calculo})"


class Vehiculo(OmniBaseModel):
    """Unidad de transporte de la flota con capacidad multidimensional y telemetría GPS."""

    TIPOS = [
        ("MOTO", "Moto / Mensajería"),
        ("PANEL", "Panel / Van"),
        ("CAMION_350", "Camión 350"),
        ("CAMION_750", "Camión 750"),
        ("GANDOLA", "Gandola / Tráiler"),
        ("EXTERNO", "Flota Externa / Delivery"),
    ]
    ESTADOS = [
        ("DISPONIBLE", "Disponible"),
        ("EN_RUTA", "En Ruta"),
        ("MANTENIMIENTO", "En Mantenimiento"),
        ("INACTIVO", "Inactivo"),
    ]

    id_vehiculo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="vehiculos_despacho")
    placa = models.CharField(max_length=25)
    marca_modelo = models.CharField(max_length=120)
    tipo_vehiculo = models.CharField(max_length=20, choices=TIPOS, default="PANEL")
    capacidad_kg = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1000.0000"))
    capacidad_m3 = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("10.0000"))
    capacidad_paletas = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    capacidad_litros = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    velocidad_promedio_kmh = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("35.00"))
    estado = models.CharField(max_length=20, choices=ESTADOS, default="DISPONIBLE", db_index=True)
    latitud_actual = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud_actual = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_actualizado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "despacho_vehiculo"
        verbose_name = "Vehículo de Despacho"
        verbose_name_plural = "Vehículos de Despacho"
        unique_together = [["id_empresa", "placa"]]
        ordering = ["placa"]
        constraints = [
            models.CheckConstraint(condition=Q(capacidad_kg__gt=0), name="desp_veh_cap_kg_gt_0"),
            models.CheckConstraint(condition=Q(capacidad_m3__gt=0), name="desp_veh_cap_m3_gt_0"),
            models.CheckConstraint(condition=Q(velocidad_promedio_kmh__gt=0), name="desp_veh_vel_gt_0"),
        ]

    def __str__(self):
        return f"{self.placa} - {self.marca_modelo} [{self.estado}]"


class Conductor(OmniBaseModel):
    """Conductor/chofer habilitado para rutas TMS propias o vinculadas."""

    id_conductor = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="conductores_despacho")
    id_empleado = models.ForeignKey(
        "rrhh.Empleado", on_delete=models.SET_NULL, null=True, blank=True, related_name="conductor_tms"
    )
    id_usuario = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfiles_conductor",
        help_text="Usuario asignado al Portal de Conductores (Plan 09 Fase 7.4).",
    )
    nombre_completo = models.CharField(max_length=150)
    cedula = models.CharField(max_length=30)
    telefono = models.CharField(max_length=30, blank=True, default="")
    licencia_grado = models.CharField(max_length=20, blank=True, default="5TA")
    licencia_vence = models.DateField(null=True, blank=True)
    id_vehiculo_asignado = models.ForeignKey(
        Vehiculo, on_delete=models.SET_NULL, null=True, blank=True, related_name="conductores"
    )
    disponible = models.BooleanField(default=True)

    class Meta:
        db_table = "despacho_conductor"
        verbose_name = "Conductor"
        verbose_name_plural = "Conductores"
        unique_together = [["id_empresa", "cedula"]]
        ordering = ["nombre_completo"]

    def clean(self):
        super().clean()
        if (
            self.id_vehiculo_asignado_id
            and self.id_empresa_id
            and self.id_vehiculo_asignado.id_empresa_id != self.id_empresa_id
        ):
            raise ValidationError({"id_vehiculo_asignado": "El vehículo no pertenece a la empresa indicada."})
        if self.id_empleado_id and self.id_empresa_id and self.id_empleado.empresa_id != self.id_empresa_id:
            raise ValidationError({"id_empleado": "El empleado no pertenece a la empresa indicada."})

    def __str__(self):
        return f"{self.nombre_completo} ({self.cedula})"


class RutaDespacho(OmniBaseModel):
    """Ruta optimizada de despacho con paradas secuenciadas, delivery externo y guía SENIAT."""

    ESTADOS = [
        ("PLANIFICADA", "Planificada"),
        ("EN_CURSO", "En Curso"),
        ("COMPLETADA", "Completada"),
        ("CANCELADA", "Cancelada"),
    ]
    PROVEEDORES_DELIVERY = [
        ("PROPIO", "Flota Propia"),
        ("SIMULADO", "Delivery Simulado"),
        ("UBER_DIRECT", "Uber Direct"),
        ("RIDERY", "Ridery"),
        ("YUMMY", "Yummy Delivery"),
    ]

    id_ruta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="rutas_despacho")
    codigo = models.CharField(max_length=50)
    fecha_ruta = models.DateField()
    id_almacen_origen = models.ForeignKey("almacenes.Almacen", on_delete=models.PROTECT, related_name="rutas_despacho")
    origen_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    origen_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    id_vehiculo = models.ForeignKey(
        Vehiculo, on_delete=models.SET_NULL, null=True, blank=True, related_name="rutas_despacho"
    )
    id_conductor = models.ForeignKey(
        Conductor, on_delete=models.SET_NULL, null=True, blank=True, related_name="rutas_despacho"
    )
    id_zona = models.ForeignKey(
        ZonaLogistica, on_delete=models.SET_NULL, null=True, blank=True, related_name="rutas_despacho"
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default="PLANIFICADA", db_index=True)
    distancia_estimada_km = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    duracion_estimada_min = models.PositiveIntegerField(default=0)
    peso_total_kg = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    volumen_total_m3 = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    costo_flete_estimado_usd = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    proveedor_delivery_externo = models.CharField(max_length=20, choices=PROVEEDORES_DELIVERY, default="PROPIO")
    referencia_delivery_externo = models.CharField(max_length=120, blank=True, default="")
    tracking_url_externo = models.URLField(max_length=500, blank=True, default="")
    id_guia_imprenta_digital = models.UUIDField(
        null=True,
        blank=True,
        help_text="UUID de fiscal.DocumentoImprentaDigital emitido como GUIA_DESPACHO.",
    )
    guia_numero_control = models.CharField(max_length=80, blank=True, default="")
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "despacho_ruta"
        verbose_name = "Ruta de Despacho"
        verbose_name_plural = "Rutas de Despacho"
        unique_together = [["id_empresa", "codigo"]]
        ordering = ["-fecha_ruta", "-fecha_creacion"]
        constraints = [
            models.CheckConstraint(condition=Q(distancia_estimada_km__gte=0), name="desp_ruta_dist_gte_0"),
            models.CheckConstraint(condition=Q(costo_flete_estimado_usd__gte=0), name="desp_ruta_flete_gte_0"),
        ]

    def clean(self):
        super().clean()
        if self.id_empresa_id:
            if self.id_almacen_origen_id and self.id_almacen_origen.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_almacen_origen": "El almacén no pertenece a la empresa."})
            if self.id_vehiculo_id and self.id_vehiculo.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_vehiculo": "El vehículo no pertenece a la empresa."})
            if self.id_conductor_id and self.id_conductor.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_conductor": "El conductor no pertenece a la empresa."})
            if self.id_zona_id and self.id_zona.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_zona": "La zona no pertenece a la empresa."})

    def __str__(self):
        return f"{self.codigo} [{self.estado}]"


class ParadaEntrega(OmniBaseModel):
    """Parada individual de entrega en una RutaDespacho con ePOD, cobro y tracking público."""

    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("EN_CAMINO", "En Camino"),
        ("ENTREGADA", "Entregada"),
        ("ENTREGA_PARCIAL", "Entrega Parcial"),
        ("RECHAZADA", "Rechazada"),
    ]

    id_parada = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="paradas_entrega")
    id_ruta = models.ForeignKey(RutaDespacho, on_delete=models.CASCADE, related_name="paradas")
    id_despacho = models.ForeignKey(Despacho, on_delete=models.PROTECT, related_name="paradas_entrega")
    id_direccion_cliente = models.ForeignKey(
        "crm.DireccionCliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paradas_entrega",
    )
    secuencia = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default="PENDIENTE", db_index=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    direccion_texto = models.TextField(blank=True, default="")
    distancia_tramo_km = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    eta_estimada = models.DateTimeField(null=True, blank=True)
    fecha_llegada_real = models.DateTimeField(null=True, blank=True)
    token_tracking = models.UUIDField(default=uuid7, unique=True, db_index=True)

    # ePOD (Electronic Proof of Delivery) y cobro en sitio
    epod_receptor_nombre = models.CharField(max_length=150, blank=True, default="")
    epod_receptor_cedula = models.CharField(max_length=40, blank=True, default="")
    epod_firma_base64 = models.TextField(blank=True, default="")
    epod_foto_url = models.CharField(max_length=500, blank=True, default="")
    epod_latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    epod_longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    epod_observaciones = models.TextField(blank=True, default="")
    motivo_rechazo = models.TextField(blank=True, default="")
    monto_cobrado_en_sitio = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    id_pago_cobro = models.ForeignKey(
        "finanzas.Pago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paradas_entrega_cobro",
    )

    class Meta:
        db_table = "despacho_parada_entrega"
        verbose_name = "Parada de Entrega"
        verbose_name_plural = "Paradas de Entrega"
        unique_together = [["id_ruta", "secuencia"]]
        ordering = ["secuencia"]
        constraints = [
            models.CheckConstraint(condition=Q(monto_cobrado_en_sitio__gte=0), name="desp_parada_cobro_gte_0"),
        ]

    def clean(self):
        super().clean()
        if self.id_empresa_id:
            if self.id_ruta_id and self.id_ruta.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_ruta": "La ruta no pertenece a la empresa."})
            if self.id_despacho_id and self.id_despacho.id_empresa_id != self.id_empresa_id:
                raise ValidationError({"id_despacho": "El despacho no pertenece a la empresa."})

    def __str__(self):
        return f"{self.id_ruta.codigo} #{self.secuencia} - {self.id_despacho.numero_despacho} [{self.estado}]"
