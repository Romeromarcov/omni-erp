from django.db import models

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


# ── Extractos y Conciliación Bancaria ─────────────────────────────────────────


class ExtractoBancarioArchivo(models.Model):
    """Corte de estado de cuenta bancario importado y validado fila a fila."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="extractos_bancarios",
    )
    id_cuenta_bancaria = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="extractos_bancarios",
    )
    formato_banco = models.CharField(max_length=30)
    nombre_archivo = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True)
    tamano_bytes = models.PositiveIntegerField(default=0)
    moneda = models.CharField(max_length=10)
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    saldo_inicial = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    saldo_final = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_debitos = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_creditos = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_lineas = models.PositiveIntegerField(default=0)
    lineas_nuevas = models.PositiveIntegerField(default=0)
    lineas_duplicadas = models.PositiveIntegerField(default=0)
    cuadra = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True, default="")
    subido_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extractos_bancarios_subidos",
    )
    activo = models.BooleanField(default=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tesoreria_extracto_bancario_archivo"
        ordering = ["-fecha_hasta", "-fecha_creacion"]
        indexes = [
            models.Index(fields=["id_empresa", "id_cuenta_bancaria", "activo"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "id_cuenta_bancaria", "sha256"],
                condition=models.Q(activo=True),
                name="uq_tesoreria_extracto_empresa_cta_sha256_activo",
            ),
        ]

    def __str__(self):
        return f"{self.nombre_archivo} ({self.formato_banco} · {self.moneda})"


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
    ORIGEN_CHOICES = [
        ("EXTRACTO", "Extracto bancario validado"),
        ("CSV", "Importado CSV"),
        ("MANUAL", "Registrado manualmente"),
        ("API", "API bancaria"),
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
    id_archivo_extracto = models.ForeignKey(
        "tesoreria.ExtractoBancarioArchivo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
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
    huella = models.CharField(max_length=24, blank=True, default="", db_index=True)
    saldo_posterior = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    orden_en_archivo = models.PositiveIntegerField(null=True, blank=True)
    codigo_operacion = models.CharField(max_length=30, blank=True, default="")
    correlativo = models.CharField(max_length=50, blank=True, default="")
    categoria_clasificacion = models.CharField(max_length=50, blank=True, default="", db_index=True)
    regla_clasificacion = models.CharField(max_length=50, blank=True, default="")
    activo = models.BooleanField(default=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    origen = models.CharField(
        max_length=20,
        choices=ORIGEN_CHOICES,
        default="MANUAL",
    )

    class Meta:
        db_table = "tesoreria_movimiento_bancario"
        ordering = ["-fecha_mov", "-fecha_creacion"]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["id_cuenta_bancaria", "fecha_mov"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "id_cuenta_bancaria", "huella"],
                condition=models.Q(activo=True) & ~models.Q(huella=""),
                name="uq_tesoreria_mov_empresa_cta_huella_activo",
            ),
        ]

    def soft_delete(self):
        self.activo = False
        self.save(update_fields=["activo"])

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


# ── Pre-conciliación determinística y cola de revisión humana ─────────────────


class ConfiguracionConciliacionCuenta(models.Model):
    """Configuración multi-tenant de reglas contables y diario externo por cuenta bancaria."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="configuraciones_conciliacion_bancaria",
    )
    id_cuenta_bancaria = models.ForeignKey(
        "finanzas.CuentaBancariaEmpresa",
        on_delete=models.CASCADE,
        related_name="configuraciones_conciliacion",
    )
    id_cuenta_comisiones = models.ForeignKey(
        "contabilidad.PlanCuentas",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configs_conciliacion_comisiones",
    )
    codigo_cuenta_comisiones = models.CharField(max_length=120, blank=True, default="")
    id_cuenta_igtf = models.ForeignKey(
        "contabilidad.PlanCuentas",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configs_conciliacion_igtf",
    )
    codigo_cuenta_igtf = models.CharField(max_length=120, blank=True, default="")
    id_cuenta_transito_pendientes = models.ForeignKey(
        "contabilidad.PlanCuentas",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configs_conciliacion_transito",
    )
    codigo_cuenta_transito_pendientes = models.CharField(max_length=120, blank=True, default="")
    id_conector_odoo = models.ForeignKey(
        "integration_hub.ConectorInstancia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configs_conciliacion_bancaria",
    )
    odoo_journal_id = models.PositiveIntegerField(null=True, blank=True)
    ventana_dias = models.PositiveSmallIntegerField(default=3)
    incluir_pagos_nativos = models.BooleanField(default=True)
    incluir_pagos_odoo = models.BooleanField(default=False)
    activo = models.BooleanField(default=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tesoreria_configuracion_conciliacion_cuenta"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["id_empresa", "activo"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "id_cuenta_bancaria"],
                condition=models.Q(activo=True),
                name="uq_tesoreria_cfg_concil_empresa_cta_activo",
            ),
        ]

    def soft_delete(self) -> None:
        self.activo = False
        self.save(update_fields=["activo", "fecha_actualizacion"])

    def __str__(self) -> str:
        return f"Reglas conciliación {self.id_cuenta_bancaria}"


class PropuestaConciliacionBancaria(models.Model):
    """Propuesta determinística (R1/R2/R3) y estado de revisión humana por movimiento bancario."""

    TIPO_CHOICES = [
        ("PAGO", "Emparejar con pago"),
        ("CUENTA", "Imputar a cuenta contable"),
        ("AMBIGUO", "Empate ambiguo entre pagos"),
        ("SIN_PROPUESTA", "Sin propuesta automática"),
    ]
    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente de revisión"),
        ("APROBADA", "Aprobada"),
        ("RECHAZADA", "Rechazada"),
        ("CORREGIDA", "Corregida manualmente"),
    ]
    FUENTE_PAGO_CHOICES = [
        ("", "Sin pago"),
        ("OMNI", "Pago nativo Omni ERP"),
        ("ODOO", "Pago externo Odoo"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="propuestas_conciliacion_bancaria",
    )
    id_movimiento_bancario = models.ForeignKey(
        "tesoreria.MovimientoBancario",
        on_delete=models.CASCADE,
        related_name="propuestas_conciliacion",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    regla = models.CharField(max_length=10, default="-")
    motivo = models.CharField(max_length=500, blank=True, default="")
    fuente_pago = models.CharField(
        max_length=10, choices=FUENTE_PAGO_CHOICES, blank=True, default=""
    )
    id_pago_nativo = models.ForeignKey(
        "finanzas.Pago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_conciliacion_bancaria",
    )
    pago_externo_id = models.CharField(max_length=64, blank=True, default="")
    pago_nombre = models.CharField(max_length=200, blank=True, default="")
    pago_socio = models.CharField(max_length=255, blank=True, default="")
    id_cuenta_contable = models.ForeignKey(
        "contabilidad.PlanCuentas",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_conciliacion_bancaria",
    )
    cuenta_contable_codigo = models.CharField(max_length=150, blank=True, default="")
    puntaje = models.PositiveSmallIntegerField(default=0)
    candidatos_json = models.JSONField(default=list, blank=True)
    estado = models.CharField(
        max_length=15, choices=ESTADO_CHOICES, default="PENDIENTE", db_index=True
    )
    ultimo_comentario = models.TextField(blank=True, default="")
    decidida_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_conciliacion_decididas",
    )
    decidida_en = models.DateTimeField(null=True, blank=True, db_index=True)
    generada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "tesoreria_propuesta_conciliacion_bancaria"
        ordering = ["-id_movimiento_bancario__fecha_mov", "-generada_en"]
        indexes = [
            models.Index(fields=["id_empresa", "estado", "activo"]),
            models.Index(fields=["id_empresa", "tipo", "activo"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "id_movimiento_bancario"],
                condition=models.Q(activo=True),
                name="uq_tesoreria_propuesta_empresa_mov_activo",
            ),
            models.UniqueConstraint(
                fields=["id_empresa", "id_pago_nativo"],
                condition=models.Q(
                    activo=True,
                    estado__in=["APROBADA", "CORREGIDA"],
                    id_pago_nativo__isnull=False,
                ),
                name="uq_tesoreria_prop_pago_nativo_aprobado",
            ),
            models.UniqueConstraint(
                fields=["id_empresa", "fuente_pago", "pago_externo_id"],
                condition=models.Q(activo=True, estado__in=["APROBADA", "CORREGIDA"])
                & ~models.Q(pago_externo_id=""),
                name="uq_tesoreria_prop_pago_ext_aprobado",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tipo} ({self.regla}) [{self.estado}] — mov {self.id_movimiento_bancario_id}"


class DecisionPreconciliacionBancaria(models.Model):
    """Bitácora inmutable de decisiones humanas sobre propuestas de conciliación bancaria."""

    ACCION_CHOICES = [
        ("APROBAR", "Aprobar propuesta"),
        ("RECHAZAR", "Rechazar propuesta"),
        ("CORREGIR", "Corregir propuesta"),
        ("REABRIR", "Reabrir propuesta"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="decisiones_preconciliacion_bancaria",
    )
    id_propuesta = models.ForeignKey(
        "tesoreria.PropuestaConciliacionBancaria",
        on_delete=models.CASCADE,
        related_name="decisiones",
    )
    id_movimiento_bancario = models.ForeignKey(
        "tesoreria.MovimientoBancario",
        on_delete=models.CASCADE,
        related_name="decisiones_preconciliacion",
    )
    accion = models.CharField(max_length=15, choices=ACCION_CHOICES, db_index=True)
    estado_anterior_json = models.JSONField(default=dict)
    estado_nuevo_json = models.JSONField(default=dict)
    comentario = models.TextField(blank=True, default="")
    id_usuario = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decisiones_preconciliacion_bancaria",
    )
    usuario_nombre = models.CharField(max_length=150, blank=True, default="")
    fecha_decision = models.DateTimeField(auto_now_add=True, db_index=True)
    activo = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "tesoreria_decision_preconciliacion_bancaria"
        ordering = ["-fecha_decision"]
        indexes = [
            models.Index(fields=["id_empresa", "fecha_decision"]),
            models.Index(fields=["id_propuesta", "fecha_decision"]),
        ]

    def __str__(self) -> str:
        return f"{self.accion} por {self.usuario_nombre or self.id_usuario_id} ({self.fecha_decision})"

