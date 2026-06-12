from decimal import Decimal

from apps.core.base_models import SoftDeleteModel
from apps.core.uuid import uuid7

from django.conf import settings
from django.db import models

from apps.inventario.models import Producto

#: Etapas estándar de una fábrica de muebles (1.I). Son la semilla por defecto;
#: cada empresa configura las suyas en ``EtapaProduccion`` (catálogo por tenant).
ETAPAS_ESTANDAR: list[tuple[str, str]] = [
    ("CORTE", "Corte"),
    ("ENSAMBLE", "Ensamble"),
    ("LIJADO", "Lijado"),
    ("PINTURA", "Pintura"),
    ("TAPIZADO", "Tapizado"),
    ("CONTROL_FINAL", "Control final"),
]


class ListaMateriales(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)  # BUG-NEW-4: R-CODE-5
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, blank=True, default='')
    documento_json = models.JSONField(blank=True, default=dict)
    producto_final = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="listas_materiales")
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, default='')

    def __str__(self):
        return self.nombre


class RutaProduccion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)  # BUG-NEW-4: R-CODE-5
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, blank=True, default='')
    documento_json = models.JSONField(blank=True, default=dict)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, default='')

    def __str__(self):
        return self.nombre


class OrdenProduccion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)  # BUG-NEW-4: R-CODE-5
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(blank=True, null=True)
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, blank=True, default='')
    documento_json = models.JSONField(blank=True, default=dict)
    tipo_operacion = models.CharField(max_length=50, blank=True, default='')
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=[
            ("pendiente", "Pendiente"),
            ("en_proceso", "En Proceso"),
            ("finalizada", "Finalizada"),
            ("cancelada", "Cancelada"),
            ("parcial", "Parcial"),
        ],
        default="pendiente",
    )
    lista_materiales = models.ForeignKey(ListaMateriales, on_delete=models.SET_NULL, null=True, blank=True)
    ruta_produccion = models.ForeignKey(RutaProduccion, on_delete=models.SET_NULL, null=True, blank=True)
    observaciones = models.TextField(blank=True, default='')

    def __str__(self):
        return f"OP-{self.id} {self.producto} ({self.estado})"


class ConsumoMaterial(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)  # BUG-NEW-4: R-CODE-5
    referencia_externa = models.CharField(max_length=100, blank=True, default='')
    documento_json = models.JSONField(blank=True, default=dict)
    orden_produccion = models.ForeignKey(OrdenProduccion, on_delete=models.CASCADE, related_name="consumos")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    # 1.I — snapshot del costo unitario del movimiento de inventario al momento
    # del consumo: el costeo real de la OF NO debe variar si costo_promedio
    # cambia después (Decimal, R-CODE-4).
    costo_unitario = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    def __str__(self):
        return f"{self.producto} x {self.cantidad} (OP {self.orden_produccion.id})"


class ProduccionTerminada(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)  # BUG-NEW-4: R-CODE-5
    referencia_externa = models.CharField(max_length=100, blank=True, default='')
    documento_json = models.JSONField(blank=True, default=dict)
    orden_produccion = models.ForeignKey(
        OrdenProduccion, on_delete=models.CASCADE, related_name="produccion_terminada"
    )
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.cantidad} terminado OP {self.orden_produccion.id}"


class ListaMaterialesDetalle(models.Model):
    id_detalle_lista = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_lista_materiales = models.ForeignKey("ListaMateriales", on_delete=models.CASCADE, related_name="detalles")
    id_producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.CASCADE, related_name="detalles_lista_materiales"
    )
    cantidad_requerida = models.DecimalField(max_digits=18, decimal_places=4)
    id_unidad_medida = models.ForeignKey(
        "inventario.UnidadMedida", on_delete=models.CASCADE, related_name="detalles_lista_materiales"
    )
    es_opcional = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True, default='')

    class Meta:
        db_table = "manufactura_lista_materiales_detalle"
        verbose_name = "Detalle de Lista de Materiales"
        verbose_name_plural = "Detalles de Lista de Materiales"

    def __str__(self):
        return f"{self.id_lista_materiales.nombre} - {self.id_producto.nombre_producto}"


class CentroTrabajo(models.Model):
    id_centro_trabajo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="centros_trabajo")
    codigo_centro = models.CharField(max_length=50)
    nombre_centro = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, default='')
    tipo_centro = models.CharField(
        max_length=20,
        choices=[
            ("MAQUINA", "Máquina"),
            ("MANUAL", "Manual"),
            ("ENSAMBLE", "Ensamble"),
            ("CONTROL_CALIDAD", "Control de Calidad"),
            ("EMPAQUE", "Empaque"),
        ],
    )
    capacidad_horas_dia = models.DecimalField(max_digits=8, decimal_places=2, default=8.00)
    costo_hora = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "manufactura_centro_trabajo"
        verbose_name = "Centro de Trabajo"
        verbose_name_plural = "Centros de Trabajo"
        unique_together = ["id_empresa", "codigo_centro"]

    def __str__(self):
        return f"{self.codigo_centro} - {self.nombre_centro}"


class OperacionProduccion(models.Model):
    id_operacion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="operaciones_produccion")
    codigo_operacion = models.CharField(max_length=50)
    nombre_operacion = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, default='')
    tiempo_estandar_minutos = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "manufactura_operacion_produccion"
        verbose_name = "Operación de Producción"
        verbose_name_plural = "Operaciones de Producción"
        unique_together = ["id_empresa", "codigo_operacion"]

    def __str__(self):
        return f"{self.codigo_operacion} - {self.nombre_operacion}"


class RutaProduccionDetalle(models.Model):
    id_detalle_ruta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_ruta_produccion = models.ForeignKey("RutaProduccion", on_delete=models.CASCADE, related_name="detalles")
    id_operacion = models.ForeignKey("OperacionProduccion", on_delete=models.CASCADE, related_name="detalles_ruta")
    id_centro_trabajo = models.ForeignKey("CentroTrabajo", on_delete=models.CASCADE, related_name="detalles_ruta")
    numero_secuencia = models.IntegerField()
    tiempo_preparacion_minutos = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    tiempo_operacion_minutos = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    observaciones = models.TextField(blank=True, default='')

    class Meta:
        db_table = "manufactura_ruta_produccion_detalle"
        verbose_name = "Detalle de Ruta de Producción"
        verbose_name_plural = "Detalles de Ruta de Producción"
        ordering = ["numero_secuencia"]

    def __str__(self):
        return f"{self.id_ruta_produccion.nombre} - Paso {self.numero_secuencia}: {self.id_operacion.nombre_operacion}"


class RegistroOperacion(models.Model):
    id_registro = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_orden_produccion = models.ForeignKey(
        "OrdenProduccion", on_delete=models.CASCADE, related_name="registros_operacion"
    )
    id_detalle_ruta = models.ForeignKey("RutaProduccionDetalle", on_delete=models.CASCADE, related_name="registros")
    id_empleado = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE, related_name="registros_operacion")
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(null=True, blank=True)
    cantidad_procesada = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    cantidad_defectuosa = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    estado = models.CharField(
        max_length=20,
        choices=[
            ("INICIADO", "Iniciado"),
            ("EN_PROGRESO", "En Progreso"),
            ("PAUSADO", "Pausado"),
            ("COMPLETADO", "Completado"),
            ("CANCELADO", "Cancelado"),
        ],
        default="INICIADO",
    )
    observaciones = models.TextField(blank=True, default='')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "manufactura_registro_operacion"
        verbose_name = "Registro de Operación"
        verbose_name_plural = "Registros de Operaciones"

    def __str__(self):
        return (
            f"OP-{self.id_orden_produccion.id} - {self.id_detalle_ruta.id_operacion.nombre_operacion} - {self.estado}"
        )


class EtapaProduccion(SoftDeleteModel):
    """Catálogo de etapas de fabricación por empresa (1.I).

    Configurable por tenant: la fábrica de muebles usa la secuencia estándar
    (corte → ensamble → lijado → pintura → tapizado → control final, ver
    ``ETAPAS_ESTANDAR``) pero cada empresa puede definir las suyas.
    ``tarifa_destajo`` permite pago a destajo: monto por unidad procesada en
    la etapa. Soft-delete vía ``activo`` (SoftDeleteModel, R-CODE-6).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="etapas_produccion")
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=100)
    orden = models.PositiveIntegerField(help_text="Posición en la secuencia de fabricación (1 = primera).")
    tarifa_destajo = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Pago a destajo por unidad procesada en esta etapa (0 = no aplica).",
    )
    descripcion = models.TextField(blank=True, default='')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "manufactura_etapa_produccion"
        verbose_name = "Etapa de Producción"
        verbose_name_plural = "Etapas de Producción"
        unique_together = ["empresa", "codigo"]
        ordering = ["orden"]

    def __str__(self):
        return f"{self.orden}. {self.nombre}"


class EtapaOrdenProduccion(models.Model):
    """Instancia de una etapa dentro de una OF concreta (1.I).

    Se materializa al crear la orden (copia de la secuencia vigente del
    catálogo) y registra la transición: quién la completó, cuándo, horas
    trabajadas × tarifa y/o pago a destajo — insumos del costeo real de
    mano de obra. Una OF no puede cerrarse con etapas pendientes.
    """

    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("completada", "Completada"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    orden_produccion = models.ForeignKey(OrdenProduccion, on_delete=models.CASCADE, related_name="etapas")
    etapa = models.ForeignKey(EtapaProduccion, on_delete=models.PROTECT, related_name="instancias")
    orden = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    horas_trabajadas = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    tarifa_hora = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    cantidad_destajo = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Unidades procesadas pagadas a destajo (tarifa_destajo de la etapa).",
    )
    pago_destajo = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    completada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="etapas_of_completadas",
    )
    fecha_completada = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True, default='')

    class Meta:
        db_table = "manufactura_etapa_orden_produccion"
        verbose_name = "Etapa de Orden de Producción"
        verbose_name_plural = "Etapas de Órdenes de Producción"
        unique_together = ["orden_produccion", "orden"]
        ordering = ["orden"]

    @property
    def costo_mano_obra(self) -> Decimal:
        """Mano de obra de la etapa: horas × tarifa + pago a destajo (Decimal)."""
        return self.horas_trabajadas * self.tarifa_hora + self.pago_destajo

    def __str__(self):
        return f"OP-{self.orden_produccion_id} · {self.orden}. {self.etapa.nombre} ({self.estado})"


class ConfiguracionManufactura(models.Model):
    """Parámetros de manufactura por empresa (1.I): overhead configurable.

    ``porcentaje_overhead`` se aplica sobre (materiales + mano de obra) al
    calcular el costo real de la OF cuando no se pasa un monto explícito de
    costos indirectos.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.OneToOneField("core.Empresa", on_delete=models.CASCADE, related_name="configuracion_manufactura")
    porcentaje_overhead = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"),
        help_text="Overhead como % sobre (materiales + mano de obra). Ej: 10 = 10%.",
    )

    class Meta:
        db_table = "manufactura_configuracion"
        verbose_name = "Configuración de Manufactura"
        verbose_name_plural = "Configuraciones de Manufactura"

    def __str__(self):
        return f"Config manufactura {self.empresa} (OH {self.porcentaje_overhead}%)"
