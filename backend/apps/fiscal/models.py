import uuid
from apps.core.uuid import uuid7

from django.db import models


class NumeroCorrelativo(models.Model):
    """Contador atómico de numeración correlativa por empresa y tipo de documento."""

    TIPOS = [
        ("FACTURA", "Factura Fiscal"),
        ("NOTA_DEBITO", "Nota de Débito"),
        ("NOTA_CREDITO", "Nota de Crédito"),
        ("NOTA_ENTREGA", "Nota de Entrega"),
        ("ORDEN_COMPRA", "Orden de Compra"),
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
