import uuid
from apps.core.uuid import uuid7

from django.db import models


class PlanCuentas(models.Model):
    id_cuenta_contable = models.UUIDField(primary_key=True, default=uuid7)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    codigo_cuenta = models.CharField(max_length=50)
    nombre_cuenta = models.CharField(max_length=255)
    tipo_cuenta = models.CharField(
        max_length=50,
        choices=[
            ("ACTIVO", "Activo"),
            ("PASIVO", "Pasivo"),
            ("PATRIMONIO", "Patrimonio"),
            ("INGRESO", "Ingreso"),
            ("GASTO", "Gasto"),
            ("COSTO", "Costo"),
        ],
    )
    naturaleza = models.CharField(max_length=10, choices=[("DEUDORA", "Deudora"), ("ACREEDORA", "Acreedora")])
    id_cuenta_padre = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)
    nivel = models.IntegerField()
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contabilidad_plan_cuentas"
        verbose_name = "Plan de Cuentas"
        verbose_name_plural = "Planes de Cuentas"
        unique_together = [["id_empresa", "codigo_cuenta"]]

    def __str__(self):
        return str(self.nombre_cuenta)


class AsientoContable(models.Model):
    id_asiento = models.UUIDField(primary_key=True, default=uuid7)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    fecha_asiento = models.DateField()
    numero_asiento = models.CharField(max_length=100)
    descripcion = models.TextField()
    id_documento_origen = models.UUIDField(null=True, blank=True)
    nombre_modelo_origen = models.CharField(max_length=100, null=True, blank=True)
    estado_asiento = models.CharField(
        max_length=20, choices=[("BORRADOR", "Borrador"), ("APROBADO", "Aprobado"), ("ANULADO", "Anulado")]
    )
    # id_usuario_registro = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE)  # Temporalmente comentado
    id_usuario_registro_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contabilidad_asiento_contable"
        verbose_name = "Asiento Contable"
        verbose_name_plural = "Asientos Contables"
        unique_together = [["id_empresa", "numero_asiento"]]

    def __str__(self):
        return str(self.numero_asiento)


class DetalleAsiento(models.Model):
    id_detalle_asiento = models.UUIDField(primary_key=True, default=uuid7)
    id_asiento = models.ForeignKey("AsientoContable", on_delete=models.CASCADE)
    id_cuenta_contable = models.ForeignKey("PlanCuentas", on_delete=models.CASCADE)
    debe = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    haber = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    descripcion_detalle = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.id_asiento)


class MapeoContable(models.Model):
    """
    Configuración de cuentas contables para cada tipo de asiento automático.
    Una fila por (empresa, tipo_asiento). Sin esta fila, generar_asiento() falla.
    """

    TIPOS_ASIENTO = [
        ("FACTURA_VENTA", "Factura de Venta"),
        ("DEVOLUCION_VENTA", "Devolución de Venta"),
        ("DEVOLUCION_VENTA_IVA", "IVA de Devolución de Venta"),
        ("FACTURA_COMPRA", "Factura de Compra"),
        ("RECEPCION_MERCANCIA", "Recepción de Mercancía"),
        ("AJUSTE_INVENTARIO", "Ajuste de Inventario"),
        ("SALIDA_INTERNA", "Salida Interna / Requisición"),
        ("PAGO_CXC", "Pago de Cuenta por Cobrar"),
        ("PAGO_CXP", "Pago de Cuenta por Pagar"),
        ("NOMINA", "Proceso de Nómina"),
        ("CAMBIO_DIVISA", "Cambio de Divisa"),
        ("PAGO_TERCERO", "Pago de Terceros"),
        ("PAGO_PARAFISCAL", "Pago de Contribución Parafiscal"),
    ]

    id_mapeo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="mapeos_contables")
    tipo_asiento = models.CharField(max_length=30, choices=TIPOS_ASIENTO)
    cuenta_debe = models.ForeignKey(
        "PlanCuentas", on_delete=models.PROTECT, related_name="mapeos_debe",
        help_text="Cuenta que va al Debe en este tipo de asiento."
    )
    cuenta_haber = models.ForeignKey(
        "PlanCuentas", on_delete=models.PROTECT, related_name="mapeos_haber",
        help_text="Cuenta que va al Haber en este tipo de asiento."
    )
    descripcion_plantilla = models.CharField(
        max_length=255, default="{tipo} - {numero}",
        help_text="Plantilla de descripción. Use {tipo}, {numero}."
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contabilidad_mapeo_contable"
        unique_together = [["id_empresa", "tipo_asiento"]]
        verbose_name = "Mapeo Contable"
        verbose_name_plural = "Mapeos Contables"

    def __str__(self):
        return f"{self.get_tipo_asiento_display()} — {self.id_empresa}"
