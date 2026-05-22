import uuid
from apps.core.uuid import uuid7

from django.db import models


class PeriodoNomina(models.Model):
    id_periodo_nomina = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="periodos_nomina")
    nombre_periodo = models.CharField(max_length=100)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    fecha_pago = models.DateField()
    tipo_periodo = models.CharField(
        max_length=15,
        choices=[("SEMANAL", "Semanal"), ("QUINCENAL", "Quincenal"), ("MENSUAL", "Mensual"), ("ANUAL", "Anual")],
    )
    estado = models.CharField(
        max_length=15,
        choices=[("ABIERTO", "Abierto"), ("PROCESANDO", "Procesando"), ("CERRADO", "Cerrado"), ("PAGADO", "Pagado")],
        default="ABIERTO",
    )
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nomina_periodo_nomina"
        verbose_name = "Período de Nómina"
        verbose_name_plural = "Períodos de Nómina"

    def __str__(self):
        return f"{self.nombre_periodo} ({self.fecha_inicio} - {self.fecha_fin})"


class ConceptoNomina(models.Model):
    id_concepto_nomina = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="conceptos_nomina")
    codigo_concepto = models.CharField(max_length=20)
    nombre_concepto = models.CharField(max_length=100)
    tipo_concepto = models.CharField(
        max_length=15,
        choices=[("DEVENGADO", "Devengado"), ("DEDUCCION", "Deducción"), ("APORTE_PATRONAL", "Aporte Patronal")],
    )
    categoria = models.CharField(
        max_length=20,
        choices=[
            ("SUELDO_BASE", "Sueldo Base"),
            ("HORAS_EXTRAS", "Horas Extras"),
            ("COMISION", "Comisión"),
            ("BONO", "Bono"),
            ("VACACIONES", "Vacaciones"),
            ("PRESTACIONES", "Prestaciones"),
            ("SEGURO_SOCIAL", "Seguro Social"),
            ("IMPUESTO_RENTA", "Impuesto sobre la Renta"),
            ("OTROS", "Otros"),
        ],
    )
    formula_calculo = models.TextField(null=True, blank=True)
    es_fijo = models.BooleanField(default=False)
    monto_fijo = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    es_porcentaje = models.BooleanField(default=False)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nomina_concepto_nomina"
        verbose_name = "Concepto de Nómina"
        verbose_name_plural = "Conceptos de Nómina"
        unique_together = [["id_empresa", "codigo_concepto"]]

    def __str__(self):
        return f"{self.codigo_concepto} - {self.nombre_concepto}"


class ProcesoNomina(models.Model):
    id_proceso_nomina = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="procesos_nomina")
    id_periodo_nomina = models.ForeignKey("PeriodoNomina", on_delete=models.CASCADE, related_name="procesos")
    numero_proceso = models.CharField(max_length=50)
    fecha_proceso = models.DateTimeField()
    total_empleados = models.IntegerField(default=0)
    total_devengado = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_deducciones = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_neto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    estado = models.CharField(
        max_length=15,
        choices=[
            ("EN_PROCESO", "En Proceso"),
            ("COMPLETADO", "Completado"),
            ("APROBADO", "Aprobado"),
            ("CANCELADO", "Cancelado"),
        ],
        default="EN_PROCESO",
    )
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nomina_proceso_nomina"
        verbose_name = "Proceso de Nómina"
        verbose_name_plural = "Procesos de Nómina"
        unique_together = [["id_empresa", "numero_proceso"]]

    def __str__(self):
        return f"{self.numero_proceso} - {self.id_periodo_nomina.nombre_periodo}"


class Nomina(models.Model):
    id_nomina = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_proceso_nomina = models.ForeignKey("ProcesoNomina", on_delete=models.CASCADE, related_name="nominas")
    id_empleado = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE, related_name="nominas")
    sueldo_base = models.DecimalField(max_digits=18, decimal_places=4)
    total_devengado = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_deducciones = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    total_neto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    dias_trabajados = models.IntegerField(default=0)
    horas_trabajadas = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    horas_extras = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    estado = models.CharField(
        max_length=15,
        choices=[("CALCULADA", "Calculada"), ("APROBADA", "Aprobada"), ("PAGADA", "Pagada")],
        default="CALCULADA",
    )
    fecha_calculo = models.DateTimeField()
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "nomina_nomina"
        verbose_name = "Nómina"
        verbose_name_plural = "Nóminas"

    def __str__(self):
        return f"{self.id_empleado.nombre} {self.id_empleado.apellido} - {self.id_proceso_nomina.numero_proceso}"


class DetalleNomina(models.Model):
    id_detalle_nomina = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_nomina = models.ForeignKey("Nomina", on_delete=models.CASCADE, related_name="detalles")
    id_concepto_nomina = models.ForeignKey("ConceptoNomina", on_delete=models.CASCADE, related_name="detalles_nomina")
    cantidad = models.DecimalField(max_digits=18, decimal_places=4, default=1.00)
    valor_unitario = models.DecimalField(max_digits=18, decimal_places=4)
    valor_total = models.DecimalField(max_digits=18, decimal_places=4)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "nomina_detalle_nomina"
        verbose_name = "Detalle de Nómina"
        verbose_name_plural = "Detalles de Nómina"

    def __str__(self):
        return f"{self.id_nomina.id_empleado.nombre} - {self.id_concepto_nomina.nombre_concepto}: {self.valor_total}"


class ProcesoNominaExtrasalarial(models.Model):
    id_proceso_extrasalarial = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="procesos_extrasalarial")
    numero_proceso = models.CharField(max_length=50)
    tipo_proceso = models.CharField(
        max_length=20,
        choices=[
            ("AGUINALDO", "Aguinaldo"),
            ("VACACIONES", "Vacaciones"),
            ("PRESTACIONES", "Prestaciones"),
            ("LIQUIDACION", "Liquidación"),
            ("BONO_ESPECIAL", "Bono Especial"),
        ],
    )
    fecha_proceso = models.DateTimeField()
    fecha_corte = models.DateField()
    total_empleados = models.IntegerField(default=0)
    total_monto = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    estado = models.CharField(
        max_length=15,
        choices=[
            ("EN_PROCESO", "En Proceso"),
            ("COMPLETADO", "Completado"),
            ("APROBADO", "Aprobado"),
            ("PAGADO", "Pagado"),
            ("CANCELADO", "Cancelado"),
        ],
        default="EN_PROCESO",
    )
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nomina_proceso_nomina_extrasalarial"
        verbose_name = "Proceso de Nómina Extrasalarial"
        verbose_name_plural = "Procesos de Nómina Extrasalarial"
        unique_together = [["id_empresa", "numero_proceso"]]

    def __str__(self):
        return f"{self.numero_proceso} - {self.tipo_proceso}"


class NominaExtrasalarial(models.Model):
    id_nomina_extrasalarial = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_proceso_extrasalarial = models.ForeignKey(
        "ProcesoNominaExtrasalarial", on_delete=models.CASCADE, related_name="nominas_extrasalarial"
    )
    id_empleado = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE, related_name="nominas_extrasalarial")
    periodo_inicio = models.DateField()
    periodo_fin = models.DateField()
    salario_promedio = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    dias_laborados = models.IntegerField(default=0)
    monto_calculado = models.DecimalField(max_digits=18, decimal_places=4)
    deducciones = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    monto_neto = models.DecimalField(max_digits=18, decimal_places=4)
    estado = models.CharField(
        max_length=15,
        choices=[("CALCULADA", "Calculada"), ("APROBADA", "Aprobada"), ("PAGADA", "Pagada")],
        default="CALCULADA",
    )
    fecha_calculo = models.DateTimeField()
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "nomina_nomina_extrasalarial"
        verbose_name = "Nómina Extrasalarial"
        verbose_name_plural = "Nóminas Extrasalariales"

    def __str__(self):
        return f"{self.id_empleado.nombre} {self.id_empleado.apellido} - {self.id_proceso_extrasalarial.tipo_proceso}"
