from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.base_models import AMBITO_CONTABLE_CHOICES, IntegrationFieldsMixin, TenantModel
from apps.core.uuid import uuid7


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
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
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


CANALES_PAGO_NOMINA_CHOICES = [
    ("TRANSFERENCIA_BS", "Transferencia Bancaria Bs"),
    ("EFECTIVO_USD", "Efectivo USD (Arqueo)"),
    ("ZELLE", "Zelle"),
    ("USDT_BINANCE", "USDT / Binance Pay"),
    ("PAGO_MOVIL", "Pago Móvil Bs"),
    ("OTRO", "Otro"),
]


class FichaSalarialDual(TenantModel, IntegrationFieldsMixin):
    """Ficha salarial dual VE: capa formal LOTTT (Bs) + paquete gerencial (USD/USDT/bonos)."""

    TIPO_CUENTA_CHOICES = [("CORRIENTE", "Corriente"), ("AHORRO", "Ahorro")]

    id_ficha = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="fichas_salariales_dual")
    id_empleado = models.OneToOneField(
        "rrhh.Empleado",
        on_delete=models.CASCADE,
        related_name="ficha_salarial_dual",
    )
    # Capa formal LOTTT (Bs / moneda_pais)
    salario_base_formal_ves = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    cestaticket_mensual_ves = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    porcentaje_ari = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    cargas_familiares = models.PositiveSmallIntegerField(default=0)
    banco_formal = models.CharField(max_length=80, blank=True, default="")
    cuenta_bancaria_formal = models.CharField(max_length=32, blank=True, default="")
    tipo_cuenta_formal = models.CharField(max_length=16, choices=TIPO_CUENTA_CHOICES, default="CORRIENTE")
    # Capa gerencial / paquete objetivo (USD / USDT / bonificaciones)
    paquete_objetivo_mensual = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    moneda_paquete = models.ForeignKey(
        "finanzas.Moneda",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fichas_salariales_paquete",
    )
    bono_fijo_gerencial = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    canal_pago_gerencial = models.CharField(max_length=24, choices=CANALES_PAGO_NOMINA_CHOICES, default="EFECTIVO_USD")
    referencia_pago_gerencial = models.CharField(max_length=120, blank=True, default="")
    activo = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "nomina_ficha_salarial_dual"
        verbose_name = "Ficha Salarial Dual"
        verbose_name_plural = "Fichas Salariales Duales"
        constraints = [
            models.CheckConstraint(
                condition=Q(salario_base_formal_ves__gte=Decimal("0")), name="ck_ficha_sal_formal_no_neg"
            ),
            models.CheckConstraint(
                condition=Q(cestaticket_mensual_ves__gte=Decimal("0")), name="ck_ficha_cestaticket_no_neg"
            ),
            models.CheckConstraint(
                condition=Q(paquete_objetivo_mensual__gte=Decimal("0")), name="ck_ficha_paquete_no_neg"
            ),
            models.CheckConstraint(
                condition=Q(bono_fijo_gerencial__gte=Decimal("0")), name="ck_ficha_bono_fijo_no_neg"
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_ari__gte=Decimal("0")) & Q(porcentaje_ari__lte=Decimal("100")),
                name="ck_ficha_ari_rango",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.id_empleado_id and self.id_empresa_id and self.id_empleado.empresa_id != self.id_empresa_id:
            raise ValidationError({"id_empleado": "El empleado no pertenece a la empresa."})

    def __str__(self) -> str:
        return f"FichaDual({self.id_empleado.cedula}) Formal={self.salario_base_formal_ves} / Obj={self.paquete_objetivo_mensual}"


class PrestamoEmpleado(TenantModel, IntegrationFieldsMixin):
    """Préstamo o adelanto de nómina con amortización automática en ámbito FISCAL o GERENCIAL."""

    ESTADO_CHOICES = [("ACTIVO", "Activo"), ("PAGADO", "Pagado"), ("ANULADO", "Anulado")]

    id_prestamo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="prestamos_empleados")
    id_empleado = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE, related_name="prestamos")
    ambito_descuento = models.CharField(
        max_length=12, choices=AMBITO_CONTABLE_CHOICES, default="GERENCIAL", db_index=True
    )
    moneda = models.ForeignKey(
        "finanzas.Moneda",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prestamos_nomina",
    )
    monto_principal = models.DecimalField(max_digits=18, decimal_places=4)
    cuotas_totales = models.PositiveSmallIntegerField(default=1)
    cuotas_pagadas = models.PositiveSmallIntegerField(default=0)
    monto_cuota = models.DecimalField(max_digits=18, decimal_places=4)
    saldo_pendiente = models.DecimalField(max_digits=18, decimal_places=4)
    fecha_otorgamiento = models.DateField(db_index=True)
    estado = models.CharField(max_length=16, choices=ESTADO_CHOICES, default="ACTIVO", db_index=True)
    observaciones = models.TextField(blank=True, default="")
    activo = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "nomina_prestamo_empleado"
        verbose_name = "Préstamo a Empleado"
        verbose_name_plural = "Préstamos a Empleados"
        ordering = ["-fecha_otorgamiento"]
        constraints = [
            models.CheckConstraint(condition=Q(monto_principal__gt=Decimal("0")), name="ck_prestamo_principal_pos"),
            models.CheckConstraint(condition=Q(monto_cuota__gt=Decimal("0")), name="ck_prestamo_cuota_pos"),
            models.CheckConstraint(condition=Q(saldo_pendiente__gte=Decimal("0")), name="ck_prestamo_saldo_no_neg"),
            models.CheckConstraint(condition=Q(cuotas_totales__gte=1), name="ck_prestamo_cuotas_tot_pos"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.id_empleado_id and self.id_empresa_id and self.id_empleado.empresa_id != self.id_empresa_id:
            raise ValidationError({"id_empleado": "El empleado no pertenece a la empresa."})

    def __str__(self) -> str:
        return f"Prestamo({self.id_empleado.cedula}) {self.saldo_pendiente}/{self.monto_principal} [{self.estado}]"


class DispersionPagoNomina(TenantModel, IntegrationFieldsMixin):
    """Registro de dispersión / orden de pago por empleado y canal (Banco Bs, Efectivo USD, Zelle, USDT)."""

    ESTADO_CHOICES = [("PENDIENTE", "Pendiente"), ("PAGADO", "Pagado"), ("ANULADO", "Anulado")]

    id_dispersion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="dispersiones_nomina")
    id_proceso_nomina = models.ForeignKey(ProcesoNomina, on_delete=models.CASCADE, related_name="dispersiones")
    id_nomina = models.ForeignKey(Nomina, on_delete=models.CASCADE, related_name="dispersiones")
    id_empleado = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE, related_name="dispersiones_pago")
    ambito = models.CharField(max_length=12, choices=AMBITO_CONTABLE_CHOICES, default="FISCAL", db_index=True)
    canal_pago = models.CharField(
        max_length=24, choices=CANALES_PAGO_NOMINA_CHOICES, default="TRANSFERENCIA_BS", db_index=True
    )
    moneda = models.ForeignKey(
        "finanzas.Moneda",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dispersiones_nomina",
    )
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    desglose_denominaciones = models.JSONField(default=dict, blank=True)
    referencia_destino = models.CharField(max_length=120, blank=True, default="")
    estado = models.CharField(max_length=16, choices=ESTADO_CHOICES, default="PENDIENTE", db_index=True)
    activo = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "nomina_dispersion_pago"
        verbose_name = "Dispersión de Pago de Nómina"
        verbose_name_plural = "Dispersiones de Pago de Nómina"
        ordering = ["-fecha_creacion"]
        constraints = [
            models.CheckConstraint(condition=Q(monto__gte=Decimal("0")), name="ck_dispersion_monto_no_neg"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.id_empleado_id and self.id_empresa_id and self.id_empleado.empresa_id != self.id_empresa_id:
            raise ValidationError({"id_empleado": "El empleado no pertenece a la empresa."})
        if (
            self.id_proceso_nomina_id
            and self.id_empresa_id
            and self.id_proceso_nomina.id_empresa_id != self.id_empresa_id
        ):
            raise ValidationError({"id_proceso_nomina": "El proceso de nómina no pertenece a la empresa."})

    def __str__(self) -> str:
        return f"Disp({self.canal_pago}) {self.id_empleado.cedula} -> {self.monto} [{self.estado}]"
