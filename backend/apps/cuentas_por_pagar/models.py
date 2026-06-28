from apps.core.uuid import uuid7

from django.db import models


class AbonoCxP(models.Model):
    id_abono_cxp = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    cuenta_por_pagar = models.ForeignKey(
        "CuentaPorPagar",
        on_delete=models.CASCADE,
        related_name="abonos",
    )
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    fecha_abono = models.DateField(auto_now_add=True)
    usuario = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    descripcion = models.TextField(blank=True, default="")
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "cuentas_por_pagar_abono_cxp"

    def __str__(self):
        return f"Abono {self.monto} → CxP {self.cuenta_por_pagar_id}"


class CuentaPorPagar(models.Model):
    id_cxp = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_proveedor = models.ForeignKey("proveedores.Proveedor", on_delete=models.CASCADE)
    id_factura_compra = models.ForeignKey(
        "compras.FacturaCompra",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cuentas_por_pagar",
    )
    # La CxP nace en la recepción (antes de que llegue la factura del proveedor);
    # este FK permite re-vincularla a la FacturaCompra cuando se registra. Sin él
    # no había forma fiable de localizar la CxP de una recepción (un proveedor
    # puede tener varias CxP abiertas). on_delete=SET_NULL: la CxP es un registro
    # financiero que debe sobrevivir si se borra la recepción.
    id_recepcion = models.ForeignKey(
        "compras.RecepcionMercancia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cuentas_por_pagar",
    )
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    monto_total = models.DecimalField(max_digits=18, decimal_places=4)
    monto_pendiente = models.DecimalField(max_digits=18, decimal_places=4)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=30,
        choices=[
            ("PENDIENTE", "Pendiente"),
            ("PAGADA", "Pagada"),
            ("ANULADA", "Anulada"),
            ("VENCIDA", "Vencida"),
            ("PARCIAL", "Parcial"),
        ],
        default="PENDIENTE",
    )
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"CxP {self.id_cxp}"


class DiferenciaCambiaria(models.Model):
    """Diferencia en cambio realizada al pagar una CxP en moneda extranjera.

    Cuando la CxP se reconoció a una tasa (``tasa_original``) y el pago se hace a
    otra (``tasa_pago``), el valor en moneda base del mismo monto en divisa
    cambia. Esa diferencia es una ganancia o pérdida cambiaria realizada que se
    registra aquí y se contabiliza (GANANCIA_CAMBIARIA / PERDIDA_CAMBIARIA).

    Para un pasivo (CxP): si la divisa se encareció (``tasa_pago`` > original),
    pagar cuesta más en moneda base → PÉRDIDA; si se abarató → GANANCIA.
    """

    id_diferencia = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_abono_cxp = models.ForeignKey(
        "AbonoCxP", on_delete=models.CASCADE, related_name="diferencias_cambiarias"
    )
    # Monto en la moneda extranjera del abono al que se aplica la diferencia.
    monto_moneda = models.DecimalField(max_digits=18, decimal_places=4)
    tasa_original = models.DecimalField(max_digits=18, decimal_places=8)
    tasa_pago = models.DecimalField(max_digits=18, decimal_places=8)
    # Diferencia en moneda base (positiva). El signo lo da ``tipo``.
    monto_diferencia = models.DecimalField(max_digits=18, decimal_places=4)
    tipo = models.CharField(
        max_length=10, choices=[("GANANCIA", "Ganancia"), ("PERDIDA", "Pérdida")]
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cuentas_por_pagar_diferencia_cambiaria"
        verbose_name = "Diferencia Cambiaria"
        verbose_name_plural = "Diferencias Cambiarias"

    def __str__(self):
        return f"Dif. cambiaria {self.tipo} {self.monto_diferencia} (abono {self.id_abono_cxp_id})"
