from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.base_models import OmniBaseModel
from apps.core.uuid import uuid7


class LotePagoBancario(OmniBaseModel):
    """Lote de pagos masivos bancarios VE (proveedores o nómina) sobre ``finanzas.CuentaBancariaEmpresa``."""

    TIPOS_LOTE = [
        ("PROVEEDORES", "Proveedores"),
        ("NOMINA", "Nómina"),
    ]

    FORMATOS_BANCO = [
        ("BANESCO_TXT", "Banesco TXT"),
        ("MERCANTIL_TXT", "Mercantil TXT"),
        ("BDV_TXT", "Banco de Venezuela TXT"),
        ("GENERICO_CSV", "Genérico CSV"),
    ]

    ESTADOS = [
        ("BORRADOR", "Borrador"),
        ("GENERADO", "Generado"),
        ("ENVIADO", "Enviado"),
        ("PROCESADO", "Procesado"),
        ("ANULADO", "Anulado"),
    ]

    id_lote_pago = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="lotes_pago_bancario",
    )
    id_cuenta_bancaria = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.PROTECT,
        related_name="lotes_pago",
    )
    tipo_lote = models.CharField(max_length=20, choices=TIPOS_LOTE)
    formato_banco = models.CharField(max_length=30, choices=FORMATOS_BANCO)
    referencia_lote = models.CharField(max_length=60)
    fecha_valor = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default="BORRADOR")
    id_proceso_nomina = models.ForeignKey(
        "nomina.ProcesoNomina",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lotes_pago_bancario",
    )
    total_registros = models.PositiveIntegerField(default=0)
    monto_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    contenido_archivo = models.TextField(blank=True, default="")
    sha256_archivo = models.CharField(max_length=64, blank=True, default="")
    nombre_archivo = models.CharField(max_length=255, blank=True, default="")
    generado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lotes_pago_generados",
    )

    class Meta:
        db_table = "banca_electronica_lote_pago"
        verbose_name = "Lote de Pago Bancario"
        verbose_name_plural = "Lotes de Pago Bancario"
        ordering = ["-fecha_valor", "-fecha_creacion"]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["id_empresa", "tipo_lote"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "referencia_lote"],
                name="banca_lote_pago_empresa_ref_uniq",
            ),
            models.CheckConstraint(
                condition=Q(monto_total__gte=0),
                name="banca_lote_pago_monto_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.referencia_lote} ({self.tipo_lote} · {self.estado})"


class DetalleLotePagoBancario(models.Model):
    """Línea individual de beneficiario dentro de un ``LotePagoBancario``."""

    id_detalle = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_lote_pago = models.ForeignKey(
        LotePagoBancario,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    id_pago = models.ForeignKey(
        "finanzas.Pago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_lote_bancario",
    )
    id_nomina = models.ForeignKey(
        "nomina.Nomina",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_lote_bancario",
    )
    beneficiario_nombre = models.CharField(max_length=200)
    beneficiario_identificacion = models.CharField(max_length=40)
    cuenta_destino = models.CharField(max_length=50)
    banco_destino = models.CharField(max_length=100, blank=True, default="")
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    referencia_linea = models.CharField(max_length=60, blank=True, default="")
    concepto = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "banca_electronica_detalle_lote_pago"
        verbose_name = "Detalle de Lote de Pago Bancario"
        verbose_name_plural = "Detalles de Lotes de Pago Bancario"
        ordering = ["id_detalle"]
        indexes = [
            models.Index(fields=["id_lote_pago"]),
            models.Index(fields=["referencia_linea"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(monto__gt=0),
                name="banca_detalle_lote_monto_gt_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.beneficiario_nombre} - {self.monto} ({self.cuenta_destino})"
