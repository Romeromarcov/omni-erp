from django.db import models

from apps.core.models import Empresa
from apps.core.uuid import uuid7
from apps.finanzas.models import Caja, Moneda


class MovimientoInternoFondo(models.Model):
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    caja_origen = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name="movimientos_salida")
    caja_destino = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name="movimientos_entrada")
    id_moneda = models.ForeignKey(
        Moneda, on_delete=models.CASCADE, related_name="movimientos_internos", null=True, blank=True
    )
    id_banco_origen = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="movimientos_banco_origen",
        null=True,
        blank=True,
    )
    id_banco_destino = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="movimientos_banco_destino",
        null=True,
        blank=True,
    )
    usuario = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, related_name="movimientos_internos", null=True, blank=True
    )
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.caja_origen} -> {self.caja_destino}: {self.monto}"


class OperacionCambioDivisa(models.Model):
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="operaciones_cambio")
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    numero_operacion = models.CharField(max_length=50)
    fecha_operacion = models.DateTimeField()
    tipo_operacion = models.CharField(max_length=20, choices=[("COMPRA", "Compra"), ("VENTA", "Venta")])
    moneda_origen = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="operaciones_origen")
    moneda_destino = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE, related_name="operaciones_destino")
    monto_origen = models.DecimalField(max_digits=18, decimal_places=4)
    tasa_cambio = models.DecimalField(max_digits=18, decimal_places=6)
    monto_destino = models.DecimalField(max_digits=18, decimal_places=4)
    comision = models.DecimalField(max_digits=18, decimal_places=4, default=0.00)
    caja_origen = models.ForeignKey(
        "finanzas.Caja", on_delete=models.CASCADE, related_name="operaciones_cambio_origen", null=True, blank=True
    )
    caja_destino = models.ForeignKey(
        "finanzas.Caja", on_delete=models.CASCADE, related_name="operaciones_cambio_destino", null=True, blank=True
    )
    banco_origen = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="operaciones_cambio_banco_origen",
        null=True,
        blank=True,
    )
    banco_destino = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="operaciones_cambio_banco_destino",
        null=True,
        blank=True,
    )
    referencia_transaccion_origen = models.CharField(max_length=100, null=True, blank=True)
    metodo_pago_origen = models.ForeignKey(
        "finanzas.MetodoPago",
        on_delete=models.CASCADE,
        related_name="operaciones_cambio_metodo_origen",
        null=True,
        blank=True,
    )
    referencia_transaccion_destino = models.CharField(max_length=100, null=True, blank=True)
    metodo_pago_destino = models.ForeignKey(
        "finanzas.MetodoPago",
        on_delete=models.CASCADE,
        related_name="operaciones_cambio_metodo_destino",
        null=True,
        blank=True,
    )
    casa_de_cambio = models.ForeignKey(
        "proveedores.Proveedor", on_delete=models.SET_NULL, null=True, blank=True, related_name="operaciones_cambio"
    )
    tipo_documento_gasto = models.CharField(max_length=50, null=True, blank=True)
    numero_documento_gasto = models.CharField(max_length=50, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tesoreria_operacion_cambio_divisa"
        verbose_name = "Operación de Cambio de Divisa"
        verbose_name_plural = "Operaciones de Cambio de Divisa"
        unique_together = [["empresa", "numero_operacion"]]

    def __str__(self):
        return f"{self.numero_operacion} - {self.tipo_operacion}: {self.monto_origen} {self.moneda_origen} -> {self.monto_destino} {self.moneda_destino}"


# ── Conciliación Bancaria ─────────────────────────────────────────────────────


class MovimientoBancario(models.Model):
    """
    Línea de extracto bancario importada desde el banco.

    Representa un movimiento real en la cuenta bancaria del banco,
    que será conciliado con los pagos/cobros registrados en el sistema.
    """

    TIPO_CHOICES = [
        ("DEBITO", "Débito"),
        ("CREDITO", "Crédito"),
    ]
    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente de conciliar"),
        ("CONCILIADO", "Conciliado"),
        ("DESCARTADO", "Descartado"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="movimientos_bancarios",
    )
    id_cuenta_bancaria = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="movimientos_bancarios",
    )
    fecha_mov = models.DateField()
    descripcion = models.CharField(max_length=300)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    referencia = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default="PENDIENTE", db_index=True)
    # FK al pago interno conciliado (null = no conciliado todavía)
    id_pago_conciliado = models.ForeignKey(
        "finanzas.Pago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_bancarios_conciliados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    origen = models.CharField(
        max_length=20,
        choices=[("CSV", "Importado CSV"), ("MANUAL", "Registrado manualmente"), ("API", "API bancaria")],
        default="MANUAL",
    )

    class Meta:
        db_table = "tesoreria_movimiento_bancario"
        ordering = ["-fecha_mov", "-fecha_creacion"]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["id_cuenta_bancaria", "fecha_mov"]),
        ]

    def __str__(self):
        return f"{self.tipo} {self.monto} — {self.descripcion[:40]} ({self.estado})"


class ConciliacionBancaria(models.Model):
    """
    Sesión de conciliación bancaria para un período y cuenta específicos.
    """

    ESTADO_CHOICES = [
        ("ABIERTA", "Abierta"),
        ("CERRADA", "Cerrada"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="conciliaciones_bancarias",
    )
    id_cuenta_bancaria = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="conciliaciones",
    )
    periodo_inicio = models.DateField()
    periodo_fin = models.DateField()
    saldo_banco = models.DecimalField(max_digits=18, decimal_places=2, help_text="Saldo según extracto bancario")
    saldo_libro = models.DecimalField(max_digits=18, decimal_places=2, help_text="Saldo según libros contables")
    diferencia = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default="ABIERTA")
    movimientos_conciliados = models.IntegerField(default=0)
    movimientos_pendientes = models.IntegerField(default=0)
    realizada_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "tesoreria_conciliacion_bancaria"
        ordering = ["-periodo_fin"]

    def __str__(self):
        return f"Conciliación {self.id_cuenta_bancaria} {self.periodo_inicio}→{self.periodo_fin} [{self.estado}]"
