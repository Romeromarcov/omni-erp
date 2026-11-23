from typing import Any

from django.db import models
from django.db.models import Q

from apps.core.base_models import OmniBaseModel
from apps.core.uuid import uuid7

AMBITO_CONTABLE_CHOICES = [
    ("FISCAL", "Fiscal"),
    ("GERENCIAL", "Gerencial"),
]


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

    def __str__(self) -> str:
        return str(self.nombre_cuenta)


class DiarioContable(OmniBaseModel):
    """Diario contable por empresa (patrón ``account.journal`` de Odoo)."""

    TIPO_CHOICES = [
        ("VENTAS", "Ventas"),
        ("COMPRAS", "Compras"),
        ("BANCO", "Banco"),
        ("CAJA", "Caja"),
        ("NOMINA", "Nómina"),
        ("VARIOS", "Varios"),
    ]

    id_diario = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="diarios_contables")
    codigo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="VARIOS")
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
        help_text="Libro al que pertenece el diario: FISCAL (normativo) o GERENCIAL.",
    )
    prefijo_secuencia = models.CharField(max_length=20, blank=True, default="")
    siguiente_numero = models.PositiveIntegerField(default=1)
    cuenta_defecto_debe = models.ForeignKey(
        "PlanCuentas", on_delete=models.SET_NULL, null=True, blank=True, related_name="diarios_debe"
    )
    cuenta_defecto_haber = models.ForeignKey(
        "PlanCuentas", on_delete=models.SET_NULL, null=True, blank=True, related_name="diarios_haber"
    )
    id_cuenta_bancaria = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diarios_contables",
    )
    id_caja = models.ForeignKey(
        "finanzas.Caja",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diarios_contables",
    )

    class Meta:
        db_table = "contabilidad_diario"
        verbose_name = "Diario Contable"
        verbose_name_plural = "Diarios Contables"
        unique_together = [["id_empresa", "codigo"]]
        indexes = [models.Index(fields=["id_empresa", "tipo", "activo"])]
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.nombre}"


class AsientoContable(models.Model):
    id_asiento = models.UUIDField(primary_key=True, default=uuid7)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_diario = models.ForeignKey(
        "DiarioContable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asientos",
    )
    asiento_revertido = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contra_asiento",
    )
    es_cierre = models.BooleanField(default=False)
    ambito = models.CharField(
        max_length=12,
        choices=AMBITO_CONTABLE_CHOICES,
        default="FISCAL",
        db_index=True,
        help_text="Libro contable del asiento: FISCAL o GERENCIAL.",
    )
    fecha_asiento = models.DateField()
    numero_asiento = models.CharField(max_length=100)
    descripcion = models.TextField()
    id_documento_origen = models.UUIDField(null=True, blank=True)
    nombre_modelo_origen = models.CharField(max_length=100, null=True, blank=True)
    estado_asiento = models.CharField(
        max_length=20, choices=[("BORRADOR", "Borrador"), ("APROBADO", "Aprobado"), ("ANULADO", "Anulado")]
    )
    # FK real al usuario que originó el asiento (deuda auditoría 2026-06-21: antes
    # solo existía el UUIDField `id_usuario_registro_temp`, que ningún flujo
    # poblaba → no había trazabilidad de quién generó cada asiento). SET_NULL: el
    # asiento es registro contable y debe sobrevivir al borrado del usuario.
    id_usuario_registro = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asientos_registrados",
    )
    id_usuario_registro_temp = models.UUIDField(null=True, blank=True)  # Deprecado por id_usuario_registro
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contabilidad_asiento_contable"
        verbose_name = "Asiento Contable"
        verbose_name_plural = "Asientos Contables"
        unique_together = [["id_empresa", "numero_asiento"]]
        indexes = [models.Index(fields=["id_empresa", "ambito", "estado_asiento", "fecha_asiento"])]

    def __str__(self) -> str:
        return str(self.numero_asiento)


class CentroCosto(OmniBaseModel):
    """Centro de costo analítico por empresa (Plan 09 Fase 1.3)."""

    TIPO_CHOICES = [
        ("OPERATIVO", "Operativo"),
        ("ADMINISTRATIVO", "Administrativo"),
        ("COMERCIAL", "Comercial"),
        ("LOGISTICA", "Logística"),
        ("PRODUCCION", "Producción"),
    ]

    id_centro_costo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="centros_costo",
    )
    codigo = models.CharField(max_length=30)
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="OPERATIVO")
    id_padre = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subcentros",
    )

    class Meta:
        db_table = "contabilidad_centro_costo"
        verbose_name = "Centro de Costo"
        verbose_name_plural = "Centros de Costo"
        unique_together = [["id_empresa", "codigo"]]
        indexes = [models.Index(fields=["id_empresa", "tipo", "activo"])]
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.nombre}"


class DetalleAsiento(models.Model):
    id_detalle_asiento = models.UUIDField(primary_key=True, default=uuid7)
    id_asiento = models.ForeignKey("AsientoContable", on_delete=models.CASCADE)
    id_cuenta_contable = models.ForeignKey("PlanCuentas", on_delete=models.CASCADE)
    id_contacto = models.ForeignKey(
        "core.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_asiento",
    )
    id_centro_costo = models.ForeignKey(
        "CentroCosto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_asiento",
    )
    debe = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    haber = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    debe_base = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    haber_base = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    debe_pais = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    haber_pais = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    debe_referencia = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    haber_referencia = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    tasa_bcv_aplicada = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    tasa_referencia_aplicada = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    descripcion_detalle = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["id_cuenta_contable", "id_contacto"]),
            models.Index(fields=["id_cuenta_contable", "id_centro_costo"]),
        ]

    def __str__(self) -> str:
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
        ("NOTA_DEBITO_FISCAL", "Nota de Débito Fiscal"),
        ("NOTA_DEBITO_FISCAL_IVA", "IVA de Nota de Débito Fiscal"),
        ("FACTURA_COMPRA", "Factura de Compra"),
        ("GASTO", "Gasto (base)"),
        ("GASTO_IVA", "IVA Crédito Fiscal de Gasto"),
        ("RECEPCION_MERCANCIA", "Recepción de Mercancía"),
        ("COSTO_VENTA", "Costo de Ventas (COGS)"),
        ("AJUSTE_INVENTARIO", "Ajuste de Inventario"),
        ("SALIDA_INTERNA", "Salida Interna / Requisición"),
        ("PAGO_CXC", "Pago de Cuenta por Cobrar"),
        ("PAGO_CXP", "Pago de Cuenta por Pagar"),
        ("GANANCIA_CAMBIARIA", "Ganancia Cambiaria"),
        ("PERDIDA_CAMBIARIA", "Pérdida Cambiaria"),
        ("NOMINA", "Proceso de Nómina"),
        ("CAMBIO_DIVISA", "Cambio de Divisa"),
        ("PAGO_TERCERO", "Pago de Terceros"),
        ("PAGO_PARAFISCAL", "Pago de Contribución Parafiscal"),
        ("RETENCION_IVA_COMPRA", "Retención IVA en Compras"),
        ("RETENCION_IVA_VENTA", "Retención IVA en Ventas"),
        ("RETENCION_ISLR", "Retención ISLR"),
    ]

    id_mapeo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="mapeos_contables")
    tipo_asiento = models.CharField(max_length=30, choices=TIPOS_ASIENTO)
    id_diario = models.ForeignKey(
        "DiarioContable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mapeos",
    )
    cuenta_debe = models.ForeignKey(
        "PlanCuentas",
        on_delete=models.PROTECT,
        related_name="mapeos_debe",
        help_text="Cuenta que va al Debe en este tipo de asiento.",
    )
    cuenta_haber = models.ForeignKey(
        "PlanCuentas",
        on_delete=models.PROTECT,
        related_name="mapeos_haber",
        help_text="Cuenta que va al Haber en este tipo de asiento.",
    )
    descripcion_plantilla = models.CharField(
        max_length=255, default="{tipo} - {numero}", help_text="Plantilla de descripción. Use {tipo}, {numero}."
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contabilidad_mapeo_contable"
        unique_together = [["id_empresa", "tipo_asiento"]]
        verbose_name = "Mapeo Contable"
        verbose_name_plural = "Mapeos Contables"

    def __str__(self) -> str:
        return f"{self.get_tipo_asiento_display()} — {self.id_empresa}"


class PeriodoContable(OmniBaseModel):
    """Período contable mensual por empresa y enlace al cierre anual."""

    ESTADO_CHOICES = [
        ("ABIERTO", "Abierto"),
        ("CERRADO", "Cerrado"),
    ]

    id_periodo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="periodos_contables")
    anio = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default="ABIERTO")
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    cerrado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periodos_contables_cerrados",
    )
    asiento_cierre = models.ForeignKey(
        "AsientoContable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periodos_cerrados",
    )
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "contabilidad_periodo_contable"
        verbose_name = "Período Contable"
        verbose_name_plural = "Períodos Contables"
        unique_together = [["id_empresa", "anio", "mes"]]
        constraints = [
            models.CheckConstraint(condition=Q(mes__gte=1, mes__lte=12), name="contabilidad_periodo_mes_1_12"),
        ]
        ordering = ["-anio", "-mes"]

    @classmethod
    def esta_cerrado(cls, empresa: Any, anio: int, mes: int) -> bool:
        """Retorna True si el período contable activo está cerrado para la empresa."""
        return cls.objects.filter(
            id_empresa=empresa,
            anio=anio,
            mes=mes,
            activo=True,
            estado="CERRADO",
        ).exists()

    def __str__(self) -> str:
        return f"{self.anio:04d}-{self.mes:02d} ({self.estado})"
