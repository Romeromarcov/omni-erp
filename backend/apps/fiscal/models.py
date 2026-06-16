import uuid
from apps.core.uuid import uuid7

from django.db import models

from apps.core.base_models import IntegrationFieldsMixin, TenantModel


class NumeroCorrelativo(models.Model):
    """Contador atómico de numeración correlativa por empresa y tipo de documento."""

    TIPOS = [
        ("FACTURA", "Factura Fiscal"),
        ("NOTA_DEBITO", "Nota de Débito"),
        ("NOTA_CREDITO", "Nota de Crédito"),
        ("NOTA_ENTREGA", "Nota de Entrega"),
        ("ORDEN_COMPRA", "Orden de Compra"),
        ("DESPACHO", "Despacho"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="numeraciones")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    prefijo = models.CharField(max_length=20, default="", blank=True, help_text='e.g. "FAC-2026-"')
    numero_actual = models.PositiveIntegerField(default=0)
    digitos = models.PositiveSmallIntegerField(default=8, help_text="Pad width, e.g. 8 → 00000001")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fiscal_numero_correlativo"
        unique_together = [["id_empresa", "tipo"]]

    def __str__(self):
        return f"{self.id_empresa} | {self.tipo} | {self.numero_actual:0{self.digitos}d}"


class Impuesto(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)
    tipo = models.CharField(
        max_length=30, choices=[("IVA", "IVA"), ("ISLR", "ISLR"), ("IGTF", "IGTF"), ("OTRO", "Otro")]
    )
    alicuota = models.DecimalField(max_digits=5, decimal_places=2)
    base_legal = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    es_generico = models.BooleanField(
        default=False, help_text="Si es True, es un impuesto global del sistema, no editable por usuarios normales."
    )
    es_publico = models.BooleanField(
        default=False, help_text="Si es True, el impuesto es visible para todas las empresas."
    )
    empresa = models.ForeignKey(
        "core.Empresa",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="impuestos_empresa",
        help_text="Empresa propietaria del impuesto. Null si es genérico.",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class ConfiguracionImpuesto(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    impuesto = models.ForeignKey(Impuesto, on_delete=models.CASCADE)
    aplica_en_venta = models.BooleanField(default=True)
    aplica_en_compra = models.BooleanField(default=False)
    aplica_si_moneda_distinta_bolivar = models.BooleanField(default=False)  # Para IGTF
    requiere_agente_retencion_iva = models.BooleanField(default=False)  # Para IGTF
    activo = models.BooleanField(default=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    # Puedes agregar más reglas según la legislación


class Retencion(models.Model):
    impuesto = models.ForeignKey(Impuesto, on_delete=models.CASCADE, related_name="retenciones")
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)
    alicuota = models.DecimalField(max_digits=5, decimal_places=2)
    agente_retencion = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="retenciones_realizadas"
    )
    sujeto_retenido = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="retenciones_recibidas")
    es_generico = models.BooleanField(
        default=False, help_text="Si es True, es una retención global del sistema, no editable por usuarios normales."
    )
    es_publico = models.BooleanField(
        default=False, help_text="Si es True, la retención es visible para todas las empresas."
    )
    empresa = models.ForeignKey(
        "core.Empresa",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="retenciones_empresa",
        help_text="Empresa propietaria de la retención. Null si es genérica.",
    )
    fecha = models.DateField()
    monto_base = models.DecimalField(max_digits=18, decimal_places=2)
    monto_retenido = models.DecimalField(max_digits=18, decimal_places=2)
    numero_comprobante = models.CharField(max_length=100, unique=True)
    referencia_documento = models.CharField(max_length=100, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)


class ContribucionParafiscal(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)
    tipo = models.CharField(
        max_length=30,
        choices=[("IVSS", "Seguro Social"), ("FAOV", "Fondo de Vivienda"), ("INCES", "INCES"), ("OTRO", "Otro")],
    )
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    base_calculo = models.CharField(
        max_length=50,
        choices=[
            ("SALARIO", "Salario"),
            ("NOMINA", "Nómina"),
            ("UTILIDAD", "Utilidad"),
            ("BONIFICACION", "Bonificación"),
            ("OTRO", "Otro"),
        ],
    )
    activo = models.BooleanField(default=True)
    es_generico = models.BooleanField(
        default=False,
        help_text="Si es True, es una contribución global del sistema, no editable por usuarios normales.",
    )
    es_publico = models.BooleanField(
        default=False, help_text="Si es True, la contribución es visible para todas las empresas."
    )
    empresa = models.ForeignKey(
        "core.Empresa",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="contribuciones_empresa",
        help_text="Empresa propietaria de la contribución. Null si es genérica.",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)


# Modelos de activación por empresa (unificados y consistentes)
class ImpuestoEmpresaActiva(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="impuestos_activos")
    impuesto = models.ForeignKey(Impuesto, on_delete=models.CASCADE, related_name="empresas_activas")
    activa = models.BooleanField(default=True)

    class Meta:
        unique_together = ("empresa", "impuesto")
        verbose_name = "Impuesto activo por empresa"
        verbose_name_plural = "Impuestos activos por empresa"

    def __str__(self):
        return f"{self.impuesto.codigo} - {self.empresa.nombre_comercial or self.empresa.nombre_legal} ({'Activo' if self.activa else 'Inactivo'})"


class RetencionEmpresaActiva(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="retenciones_activas")
    retencion = models.ForeignKey(Retencion, on_delete=models.CASCADE, related_name="empresas_activas")
    activa = models.BooleanField(default=True)

    class Meta:
        unique_together = ("empresa", "retencion")
        verbose_name = "Retención activa por empresa"
        verbose_name_plural = "Retenciones activas por empresa"

    def __str__(self):
        return f"{self.retencion.codigo} - {self.empresa.nombre_comercial or self.empresa.nombre_legal} ({'Activa' if self.activa else 'Inactiva'})"


class ContribucionEmpresaActiva(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="contribuciones_activas")
    contribucion = models.ForeignKey(ContribucionParafiscal, on_delete=models.CASCADE, related_name="empresas_activas")
    activa = models.BooleanField(default=True)

    class Meta:
        unique_together = ("empresa", "contribucion")
        verbose_name = "Contribución activa por empresa"
        verbose_name_plural = "Contribuciones activas por empresa"

    def __str__(self):
        return f"{self.contribucion.codigo} - {self.empresa.nombre_comercial or self.empresa.nombre_legal} ({'Activa' if self.activa else 'Inactiva'})"


# Modelo personalizado para empresa y contribución parafiscal
class EmpresaContribucionParafiscal(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    contribucion = models.ForeignKey(ContribucionParafiscal, on_delete=models.CASCADE)
    porcentaje_personalizado = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)


class ConfiguracionRetencion(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, help_text="Agente de retención")
    impuesto = models.ForeignKey(Impuesto, on_delete=models.CASCADE)
    aplica_en_venta = models.BooleanField(default=True)
    aplica_en_compra = models.BooleanField(default=False)
    aplica_si_moneda_distinta_bolivar = models.BooleanField(default=False)  # Ejemplo IGTF
    aplica_si_monto_mayor = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    aplica_si_tipo_cliente = models.CharField(max_length=30, null=True, blank=True)  # Ej: 'contribuyente especial'
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Retención {self.impuesto.nombre} ({self.empresa}) {self.porcentaje}%"


# ── Modelos fiscales venezolanos (IVA / IGTF) ─────────────────────────────────


class ConfiguracionFiscalEmpresa(models.Model):
    """Parámetros fiscales globales de una empresa (IVA, IGTF)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.OneToOneField(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="configuracion_fiscal",
    )
    contribuyente_iva = models.BooleanField(default=True)
    aplica_igtf = models.BooleanField(default=True)
    tasa_igtf = models.DecimalField(max_digits=5, decimal_places=4, default="0.03")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fiscal_configuracion_empresa"

    def __str__(self):
        return f"Fiscal {self.id_empresa}"


class TasaIVAEmpresa(models.Model):
    """Tasas de IVA configuradas por empresa (GENERAL/REDUCIDO/EXENTO)."""

    TIPOS = [
        ("GENERAL", "General"),
        ("REDUCIDO", "Reducido"),
        ("EXENTO", "Exento"),
        ("ADICIONAL", "Adicional"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tasas_iva",
    )
    tipo = models.CharField(max_length=10, choices=TIPOS)
    nombre = models.CharField(max_length=50)
    tasa = models.DecimalField(max_digits=7, decimal_places=6)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fiscal_tasa_iva_empresa"
        unique_together = [["id_empresa", "tipo"]]

    def __str__(self):
        return f"{self.nombre} ({float(self.tasa) * 100:.0f}%)"


# ── Pago de contribuciones parafiscales (Capa B §6.7, plan §6.3) ──────────────


class PagoContribucionParafiscal(TenantModel, IntegrationFieldsMixin):
    """
    Pago de una contribución parafiscal (IVSS, FAOV/BANAVIH, INCES, RPE/paro
    forzoso…) calculada por la nómina, para un período mensual (año + mes).

    Ciclo de vida (las transiciones las gobiernan los services de
    ``apps.fiscal.services_parafiscales`` — transición inválida → 400)::

        pendiente ──pagar──→ pagado    (egreso en caja/banco + Pago genérico
                                        + asiento PAGO_PARAFISCAL, R-CODE-11)
        pendiente ──anular─→ anulado   (sin efectos financieros que revertir)

    No-doble-pago: a nivel de BD solo puede existir UNA fila no anulada por
    ``(empresa, contribución, período)`` — ver el ``UniqueConstraint``
    condicional. Anular libera el período para re-declarar.

    El pago efectivo reusa el flujo financiero canónico: se crea un
    ``finanzas.Pago`` (EGRESO, tipo_documento=IMPUESTO) y
    ``registrar_efectos_pago`` genera la TransaccionFinanciera + el
    ``MovimientoCajaBanco`` de egreso (visible en el libro maestro de caja,
    §6.8) con ``select_for_update`` sobre la caja/cuenta afectada.
    """

    ESTADO_CHOICES = [
        ("pendiente", "Pendiente de pago"),
        ("pagado", "Pagado"),
        ("anulado", "Anulado"),
    ]

    id_pago_parafiscal = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="pagos_parafiscales"
    )
    contribucion = models.ForeignKey(
        "ContribucionParafiscal",
        on_delete=models.PROTECT,
        related_name="pagos_parafiscales",
        help_text="Contribución parafiscal que se paga (IVSS, FAOV, INCES…).",
    )
    periodo_año = models.PositiveSmallIntegerField(
        help_text="Año del período declarado (ej. 2026)."
    )
    periodo_mes = models.PositiveSmallIntegerField(
        help_text="Mes del período declarado (1–12)."
    )
    monto = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Monto a pagar de la contribución para el período (R-CODE-4).",
    )
    id_moneda = models.ForeignKey(
        "finanzas.Moneda", on_delete=models.PROTECT, related_name="pagos_parafiscales"
    )
    referencia = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Referencia del pago (planilla, comprobante o transferencia).",
    )
    id_proceso_nomina = models.ForeignKey(
        "nomina.ProcesoNomina",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_parafiscales",
        help_text="Proceso de nómina del que proviene el cálculo (trazabilidad, opcional).",
    )
    estado = models.CharField(
        max_length=15, choices=ESTADO_CHOICES, default="pendiente", db_index=True
    )
    fecha_pago = models.DateField(
        null=True, blank=True, help_text="Fecha en que se ejecutó el pago (se fija al pagar)."
    )
    # Trazabilidad del documento financiero generado por la acción 'pagar'
    # (SET_NULL: si el Pago se eliminara, este registro conserva su historia).
    id_pago = models.ForeignKey(
        "finanzas.Pago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_parafiscales",
        help_text="Pago genérico de finanzas generado por la acción 'pagar'.",
    )

    class Meta:
        db_table = "fiscal_pago_contribucion_parafiscal"
        verbose_name = "Pago de Contribución Parafiscal"
        verbose_name_plural = "Pagos de Contribuciones Parafiscales"
        ordering = ["-periodo_año", "-periodo_mes", "-fecha_creacion"]
        constraints = [
            # No doble pago: solo una fila NO anulada por período + contribución.
            models.UniqueConstraint(
                fields=["id_empresa", "contribucion", "periodo_año", "periodo_mes"],
                condition=~models.Q(estado="anulado"),
                name="uniq_pago_parafiscal_periodo_no_anulado",
            ),
            # Backstop de BD del validate() del serializer (bugs lote 4): un
            # período imposible no entra ni por ORM directo / scripts.
            models.CheckConstraint(
                condition=models.Q(periodo_mes__gte=1, periodo_mes__lte=12),
                name="ck_pago_parafiscal_mes_entre_1_y_12",
            ),
            models.CheckConstraint(
                condition=models.Q(periodo_año__gte=2000, periodo_año__lte=2100),
                name="ck_pago_parafiscal_anio_entre_2000_y_2100",
            ),
        ]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["id_empresa", "periodo_año", "periodo_mes"]),
        ]

    def __str__(self):
        return (
            f"{self.contribucion.codigo} {self.periodo_año:04d}-{self.periodo_mes:02d} "
            f"— {self.monto} [{self.estado}]"
        )

    @property
    def periodo(self) -> str:
        """Período en formato 'YYYY-MM' (para API y reportes)."""
        return f"{self.periodo_año:04d}-{self.periodo_mes:02d}"


# ── Período Fiscal ─────────────────────────────────────────────────────────────


class PeriodoFiscal(models.Model):
    """
    Registro de cierre de período mensual por empresa.

    Una vez cerrado (cerrado=True) no se pueden emitir ni modificar
    documentos fiscales en ese período.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="periodos_fiscales",
    )
    año = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    cerrado = models.BooleanField(default=False)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    cerrado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fiscal_periodo_fiscal"
        unique_together = [["id_empresa", "año", "mes"]]

    def __str__(self):
        return f"{self.id_empresa} — {self.año:04d}/{self.mes:02d} ({'CERRADO' if self.cerrado else 'abierto'})"

    @classmethod
    def esta_cerrado(cls, empresa, año: int, mes: int) -> bool:
        """Retorna True si el período (año, mes) está cerrado para la empresa."""
        return cls.objects.filter(
            id_empresa=empresa, año=año, mes=mes, cerrado=True
        ).exists()
