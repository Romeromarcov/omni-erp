import uuid
from apps.core.uuid import uuid7

from django.conf import settings
from django.db import models
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.utils import timezone


class Moneda(models.Model):
    id_moneda = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    TIPO_MONEDA_CHOICES = [
        ("fiat", "Fiat"),
        ("crypto", "Cripto"),
        ("otro", "Otro"),
    ]
    tipo_moneda = models.CharField(max_length=10, choices=TIPO_MONEDA_CHOICES, default="fiat")
    codigo_iso = models.CharField(max_length=5, unique=True)  # Ej: 'USD', 'EUR', 'VES', 'USDT', 'WBTC'
    nombre = models.CharField(max_length=50)
    pais_codigo_iso = models.CharField(max_length=3, null=True, blank=True, verbose_name="Código ISO del País")
    pais_nombre = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nombre del País")
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    simbolo = models.CharField(max_length=5)
    decimales = models.IntegerField(default=2)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    es_generica = models.BooleanField(
        default=False, help_text="Si es True, es una moneda global del sistema, no editable por usuarios normales."
    )
    es_publica = models.BooleanField(
        default=False, help_text="Si es True, la moneda es visible para todas las empresas."
    )
    empresa = models.ForeignKey(
        "core.Empresa",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="monedas_empresa",
        help_text="Empresa propietaria de la moneda. Null si es genérica.",
    )

    def __str__(self):
        return f"{self.nombre} ({self.codigo_iso})"


# Modelo para métodos de pago activos por empresa
class MetodoPagoEmpresaActiva(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="metodos_pago_activos")
    metodo_pago = models.ForeignKey("MetodoPago", on_delete=models.CASCADE, related_name="empresas_activas")
    activa = models.BooleanField(default=True)


# Modelo para monedas activas por empresa
class MonedaEmpresaActiva(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="monedas_activas")
    moneda = models.ForeignKey("Moneda", on_delete=models.CASCADE, related_name="empresas_activas")
    activa = models.BooleanField(default=True)


class TasaCambio(models.Model):
    id_tasa_cambio = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Para OFICIAL_BCV puede ser null y será global para todas las empresas.",
    )
    id_moneda_origen = models.ForeignKey("Moneda", related_name="tasa_origen", on_delete=models.CASCADE)
    id_moneda_destino = models.ForeignKey("Moneda", related_name="tasa_destino", on_delete=models.CASCADE)
    tipo_tasa = models.CharField(
        max_length=20,
        choices=[
            ("OFICIAL_BCV", "Oficial BCV"),
            ("ESPECIAL_USUARIO", "Especial Usuario"),
            ("PROMEDIO_MERCADO", "Promedio Mercado"),
            ("FIJA", "Fija"),
        ],
    )
    valor_tasa = models.DecimalField(max_digits=18, decimal_places=8)
    fecha_tasa = models.DateField()
    hora_tasa = models.TimeField(null=True, blank=True)
    id_usuario_registro = models.ForeignKey("core.Usuarios", null=True, blank=True, on_delete=models.SET_NULL)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)


class MetodoPago(models.Model):
    id_metodo_pago = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey(
        "core.Empresa",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="metodos_pago_empresa",
        help_text="Empresa propietaria del método. Null si es genérico.",
    )
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    nombre_metodo = models.CharField(max_length=100)
    tipo_metodo = models.CharField(
        max_length=50,
        choices=[
            ("EFECTIVO", "Efectivo"),
            ("ELECTRONICO", "Electrónico"),
            ("TARJETA", "Tarjeta"),
            ("CHEQUE", "Cheque"),
            ("CREDITO", "Crédito"),
            ("OTRO", "Otro"),
        ],
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # NUEVOS CAMPOS PARA MULTI-TENANT Y VISIBILIDAD
    es_generico = models.BooleanField(
        default=False, help_text="Si es True, es un método global del sistema, no editable por usuarios normales."
    )
    es_publico = models.BooleanField(
        default=False, help_text="Si es True, el método es visible para todas las empresas."
    )
    monedas = models.ManyToManyField(
        "Moneda", related_name="metodopago_monedas", blank=True, help_text="Monedas aceptadas por este método de pago."
    )

    def __str__(self):
        return self.nombre_metodo

    class Meta:
        db_table = "finanzas_metodo_pago"
        verbose_name = "Método de Pago"
        verbose_name_plural = "Métodos de Pago"


class TransaccionFinanciera(models.Model):
    TIPOS_TRANSACCION = [
        ("INGRESO", "Ingreso"),
        ("EGRESO", "Egreso"),
    ]

    id_transaccion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="transacciones_financieras")
    fecha_hora_transaccion = models.DateTimeField()
    tipo_transaccion = models.CharField(max_length=20, choices=TIPOS_TRANSACCION)
    monto_transaccion = models.DecimalField(max_digits=18, decimal_places=2)
    id_moneda_transaccion = models.ForeignKey("Moneda", on_delete=models.CASCADE, related_name="transacciones_moneda")
    id_moneda_base = models.ForeignKey(
        "Moneda",
        on_delete=models.CASCADE,
        related_name="transacciones_base",
        help_text="Moneda base de la empresa para la transacción.",
        null=True,
        blank=True,
    )
    id_moneda_pais_empresa = models.ForeignKey(
        "Moneda",
        on_delete=models.CASCADE,
        related_name="transacciones_pais_empresa",
        help_text="Moneda país de la empresa para la transacción.",
        null=True,
        blank=True,
    )
    monto_moneda_pais = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monto equivalente en moneda país de la empresa.",
    )
    monto_base_empresa = models.DecimalField(max_digits=18, decimal_places=2)
    id_metodo_pago = models.ForeignKey("MetodoPago", on_delete=models.CASCADE, related_name="transacciones")
    referencia_pago = models.CharField(max_length=100, null=True, blank=True)
    descripcion = models.TextField(null=True, blank=True)
    tipo_documento_asociado = models.CharField(
        max_length=20,
        choices=[
            ("COMPRA", "Compra"),
            ("VENTA", "Venta"),
            ("GASTO", "Gasto"),
            ("NOMINA", "Nómina"),
            ("AJUSTE", "Ajuste"),
        ],
        null=True,
        blank=True,
    )
    nro_documento_asociado = models.CharField(max_length=100, null=True, blank=True)
    id_caja = models.ForeignKey(
        "Caja", on_delete=models.SET_NULL, null=True, blank=True, related_name="transacciones_financieras"
    )
    id_cuenta_bancaria = models.ForeignKey(
        "CuentaBancariaEmpresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transacciones_financieras",
    )
    id_usuario_registro = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, related_name="transacciones_registradas"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finanzas_transaccion_financiera"
        verbose_name = "Transacción Financiera"
        verbose_name_plural = "Transacciones Financieras"

    def __str__(self):
        return f"{self.tipo_transaccion} - {self.monto_transaccion}"


# Modelo unificado y flexible para todo tipo de caja (registradora, gerencia, matriz, etc.)


# Modelo unificado para cajas virtuales (creadas dinámicamente desde plantillas)
class Caja(models.Model):
    metodos_pago = models.ManyToManyField(
        "MetodoPago",
        related_name="cajas_virtuales",
        blank=True,
        help_text="Métodos de pago permitidos para esta caja virtual.",
    )

    TIPO_CAJA_CHOICES = [
        ("REGISTRADORA", "Caja Registradora Virtual"),
        ("GERENCIA", "Caja Gerente Virtual"),
        ("MATRIZ", "Caja Matriz Virtual"),
        ("OTRO", "Otro Virtual"),
    ]

    id_caja = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="cajas_virtuales", null=True, blank=True
    )
    sucursal = models.ForeignKey(
        "core.Sucursal", on_delete=models.SET_NULL, null=True, blank=True, related_name="cajas_virtuales"
    )
    nombre = models.CharField(max_length=100)
    tipo_caja = models.CharField(max_length=20, choices=TIPO_CAJA_CHOICES, default="REGISTRADORA")
    descripcion = models.TextField(blank=True, null=True)
    moneda = models.ForeignKey("Moneda", on_delete=models.CASCADE, related_name="cajas_virtuales")
    activa = models.BooleanField(default=True)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # Asociación con caja física
    caja_fisica = models.ForeignKey(
        "CajaFisica", on_delete=models.CASCADE, null=True, blank=True, related_name="cajas_virtuales"
    )

    # Asociación con plantilla maestra (opcional, para cajas virtuales basadas en plantillas)
    plantilla_maestro = models.ForeignKey(
        "PlantillaMaestroCajasVirtuales",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cajas_virtuales",
    )

    # Saldo actual de la caja virtual
    saldo_actual = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)

    class Meta:
        db_table = "finanzas_caja_virtual"
        verbose_name = "Caja Virtual"
        verbose_name_plural = "Cajas Virtuales"
        ordering = ["empresa", "nombre"]

    def __str__(self):
        return f"{self.nombre} (Virtual - {self.get_tipo_caja_display()}) - {self.moneda.codigo_iso}"

    def realizar_cierre(self, saldo_real, usuario=None, hasta=None):
        """
        Realiza el cierre de la caja virtual (FIX endpoint roto: el endpoint
        ``POST /finanzas/cajas/{id}/cierre/`` llamaba este método, que no
        existía → siempre 400). Reutiliza el patrón de corte persistente del
        PR #73 (MovimientoCajaBanco tipo 'CIERRE'); además reconcilia
        ``saldo_actual`` con el saldo real contado. Ver
        ``services.realizar_cierre_caja``.
        """
        from .services import realizar_cierre_caja

        return realizar_cierre_caja(self, saldo_real, usuario=usuario, hasta=hasta)


# Modelo para cajas físicas (puestos de trabajo con hardware específico)
class CajaFisica(models.Model):

    def realizar_cierre(self, saldo_real, usuario=None, hasta=None):
        """
        Realiza el cierre de caja física (FIX hallazgo P0-8 / PR #73):
        - Calcula ingresos y egresos desde el último corte (movimiento
          'CIERRE'), compara con el saldo real contado, crea ajuste si hay
          descuadre y persiste el corte como MovimientoCajaBanco 'CIERRE'.
        - La lógica común (también usada por Caja virtual) vive en
          ``services.realizar_cierre_caja``.
        """
        from .services import realizar_cierre_caja

        return realizar_cierre_caja(self, saldo_real, usuario=usuario, hasta=hasta)

    def metodo_pago_deshabilitado(self, metodo_pago):
        """FIX: este método no existía y las plantillas maestras lo invocaban →
        AttributeError. Devuelve True si hay un override que deshabilita el
        método de pago para esta caja física."""
        return self.metodo_pago_overrides.filter(metodo_pago=metodo_pago, deshabilitado=True).exists()

    TIPO_CAJA_CHOICES = [
        ("REGISTRADORA", "Caja Registradora"),
        ("GERENCIA", "Caja Gerente Sucursal"),
        ("MATRIZ", "Caja Matriz/Principal"),
        ("OTRO", "Otro"),
    ]

    id_caja_fisica = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="cajas_fisicas", null=True, blank=True
    )
    sucursal = models.ForeignKey(
        "core.Sucursal", on_delete=models.SET_NULL, null=True, blank=True, related_name="cajas_fisicas"
    )
    nombre = models.CharField(max_length=100)
    tipo_caja = models.CharField(max_length=20, choices=TIPO_CAJA_CHOICES, default="REGISTRADORA")
    descripcion = models.TextField(blank=True, null=True)
    activa = models.BooleanField(default=True)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # CAMPOS DEL DISPOSITIVO
    nombre_dispositivo = models.CharField(
        max_length=100, default="", help_text="Nombre descriptivo del dispositivo físico"
    )
    tipo_dispositivo = models.CharField(
        max_length=20,
        choices=[
            ("PC", "Computadora Personal"),
            ("TABLET", "Tablet"),
            ("MOVIL", "Teléfono Móvil"),
            ("TERMINAL", "Terminal de Pago"),
            ("OTRO", "Otro"),
        ],
        default="PC",
        help_text="Tipo de dispositivo físico",
    )
    identificador_dispositivo = models.CharField(
        max_length=100, default="", unique=True, help_text="Identificador único del dispositivo (MAC, serial, UUID)"
    )
    descripcion_dispositivo = models.TextField(blank=True, null=True, help_text="Descripción del dispositivo")
    ultima_conexion_dispositivo = models.DateTimeField(
        null=True, blank=True, help_text="Última vez que el dispositivo se conectó al sistema"
    )

    # CAMPOS ESPECÍFICOS PARA CAJAS FÍSICAS
    requiere_sesion_activa = models.BooleanField(
        default=True, help_text="Si es True, requiere que un usuario tenga una sesión activa para operar"
    )

    class Meta:
        db_table = "finanzas_caja_fisica"
        verbose_name = "Caja Física"
        verbose_name_plural = "Cajas Físicas"

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_caja_display()}) - {self.nombre_dispositivo}"

    @property
    def cajas_virtuales_asociadas(self):
        """Retorna las cajas virtuales asociadas a esta caja física"""
        return self.cajas_virtuales.all()

    @property
    def sesion_activa(self):
        """Retorna la sesión activa de esta caja física, si existe"""
        return self.sesiones.filter(estado="ABIERTA").first()

    @property
    def esta_abierta(self):
        """Retorna True si la caja tiene una sesión activa"""
        return self.sesion_activa is not None

    @property
    def usuario_actual(self):
        """Retorna el usuario que tiene la sesión activa, si existe"""
        sesion = self.sesion_activa
        return sesion.usuario if sesion else None

    @property
    def nombre_usuario_actual(self):
        """Retorna el nombre del usuario que tiene la sesión activa"""
        usuario = self.usuario_actual
        return usuario.username if usuario else None

    @property
    def estado_sesion_display(self):
        """Retorna el estado de la sesión en formato legible"""
        if self.esta_abierta:
            usuario = self.nombre_usuario_actual
            return f"Abierta por {usuario}" if usuario else "Abierta"
        return "Cerrada"


# Modelo para asociar cajas físicas a usuarios
class CajaFisicaUsuario(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    usuario = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE, related_name="cajas_fisicas_asignadas")
    caja_fisica = models.ForeignKey("CajaFisica", on_delete=models.CASCADE, related_name="usuarios_asignados")
    es_predeterminada = models.BooleanField(
        default=False, help_text="Si es True, esta caja física será sugerida por defecto para este usuario."
    )

    # Permisos específicos para operaciones de sesión (extensible para el futuro)
    puede_abrir_sesion = models.BooleanField(
        default=True, help_text="Si es True, el usuario puede abrir sesiones en esta caja física."
    )
    puede_cerrar_sesion = models.BooleanField(
        default=True, help_text="Si es True, el usuario puede cerrar sesiones en esta caja física."
    )

    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finanzas_caja_fisica_usuario"
        verbose_name = "Caja Física de Usuario"
        verbose_name_plural = "Cajas Físicas de Usuarios"
        unique_together = ["usuario", "caja_fisica"]

    def __str__(self):
        return f"{self.usuario.username} - {self.caja_fisica.nombre}"


# Modelo para asociar cajas virtuales a usuarios
class CajaVirtualUsuario(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    usuario = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE, related_name="cajas_virtuales_asignadas")
    caja_virtual = models.ForeignKey("Caja", on_delete=models.CASCADE, related_name="usuarios_virtuales_asignados")
    es_predeterminada = models.BooleanField(
        default=False, help_text="Si es True, esta caja virtual será sugerida por defecto para este usuario."
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finanzas_caja_virtual_usuario"
        verbose_name = "Caja Virtual de Usuario"
        verbose_name_plural = "Cajas Virtuales de Usuarios"
        unique_together = ["usuario", "caja_virtual"]

    def __str__(self):
        return f"{self.usuario.username} - {self.caja_virtual.nombre}"


# Modelo para asociar cajas a usuarios (LEGACY - mantener por compatibilidad)
class CajaUsuario(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    usuario = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE, related_name="cajas_asignadas")
    caja = models.ForeignKey("Caja", on_delete=models.CASCADE, related_name="usuarios_asignados")
    es_predeterminada = models.BooleanField(
        default=False, help_text="Si es True, esta caja será sugerida por defecto para este usuario."
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finanzas_caja_usuario"
        verbose_name = "Caja de Usuario (Legacy)"
        verbose_name_plural = "Cajas de Usuarios (Legacy)"
        unique_together = ["usuario", "caja"]

    def __str__(self):
        return f"{self.usuario.username} - {self.caja.nombre}"


class CuentaBancariaEmpresa(models.Model):
    metodos_pago = models.ManyToManyField(
        "MetodoPago",
        related_name="cuentas_bancarias",
        blank=True,
        help_text="Métodos de pago permitidos para esta cuenta bancaria.",
    )
    monedas = models.ManyToManyField(
        "Moneda",
        related_name="cuentabancaria_monedas",
        blank=True,
        help_text="Monedas aceptadas por esta cuenta bancaria.",
    )
    TIPOS_CUENTA = [
        ("AHORRO", "Ahorro"),
        ("CORRIENTE", "Corriente"),
        ("CREDITO", "Crédito"),
    ]

    id_cuenta_bancaria = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="cuentas_bancarias_finanzas")
    nombre_banco = models.CharField(max_length=100)
    numero_cuenta = models.CharField(max_length=50, unique=True)
    tipo_cuenta = models.CharField(max_length=50, choices=TIPOS_CUENTA)
    id_moneda = models.ForeignKey("Moneda", on_delete=models.CASCADE, related_name="cuentas_bancarias_finanzas")
    saldo_actual = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finanzas_cuenta_bancaria_empresa"
        verbose_name = "Cuenta Bancaria Empresa"
        verbose_name_plural = "Cuentas Bancarias Empresa"
        ordering = ["id_empresa", "nombre_banco"]

    def __str__(self):
        return f"{self.nombre_banco} - {self.numero_cuenta}"


class Datafono(models.Model):
    def realizar_cierre(self, usuario=None, hasta=None):
        """
        Realiza el cierre del datafono:
        - Marca como conciliadas las transacciones no conciliadas hasta la fecha/hora indicada (o ahora).
        - Crea un MovimientoCajaBanco con el neto a depositar (total menos comisión).
        - Actualiza saldo_temporal, fecha_ultimo_cierre y la cuenta bancaria asociada.
        - Devuelve un resumen del cierre.
        """
        from decimal import Decimal

        from django.db import transaction
        from django.utils import timezone

        from .models import MovimientoCajaBanco, TransaccionDatafono

        if not self.id_cuenta_bancaria_asociada:
            raise ValueError("El datafono no tiene cuenta bancaria asociada para el cierre.")

        ahora = timezone.now()
        limite = hasta or ahora
        # Buscar transacciones no conciliadas hasta el límite
        transacciones = self.transacciones_datafono.filter(conciliada=False, fecha_hora_transaccion__lte=limite)
        if self.fecha_ultimo_cierre:
            transacciones = transacciones.filter(fecha_hora_transaccion__gt=self.fecha_ultimo_cierre)
        total = sum((t.monto for t in transacciones), Decimal("0.00"))
        comision = total * (self.comision_porcentaje / Decimal("100"))
        neto = total - comision

        if total == 0:
            return {
                "total": total,
                "comision": comision,
                "neto": neto,
                "movimiento_id": None,
                "transacciones_conciliadas": 0,
                "fecha_cierre": limite,
                "mensaje": "No hay transacciones pendientes de cierre.",
            }

        with transaction.atomic():
            # Crear movimiento en cuenta bancaria asociada
            saldo_anterior = self.id_cuenta_bancaria_asociada.saldo_actual
            movimiento = MovimientoCajaBanco.objects.create(
                id_empresa=self.id_empresa,
                fecha_movimiento=limite.date(),
                hora_movimiento=limite.time(),
                tipo_movimiento="INGRESO",
                monto=neto,
                id_moneda=self.id_cuenta_bancaria_asociada.id_moneda,
                concepto=f"Depósito cierre datafono {self.nombre}",
                referencia=f'Cierre {self.serial} {limite.strftime("%Y-%m-%d %H:%M:%S")}',
                id_cuenta_bancaria=self.id_cuenta_bancaria_asociada,
                saldo_anterior=saldo_anterior,
                saldo_nuevo=saldo_anterior + neto,
                id_usuario_registro=usuario if usuario else None,
            )

            # Crear transacción financiera por la comisión bancaria (gasto operativo)
            if comision > 0:
                from .models import MetodoPago, TransaccionFinanciera

                # Buscar método de pago para comisiones bancarias
                metodo_comision = MetodoPago.objects.filter(nombre_metodo__icontains="comisión", activo=True).first()

                if not metodo_comision:
                    # Si no existe, buscar uno genérico para gastos bancarios
                    metodo_comision = MetodoPago.objects.filter(nombre_metodo__icontains="banco", activo=True).first()

                if metodo_comision:
                    TransaccionFinanciera.objects.create(
                        id_empresa=self.id_empresa,
                        fecha_hora_transaccion=limite,
                        tipo_transaccion="EGRESO",
                        monto_transaccion=comision,
                        id_moneda_transaccion=self.id_cuenta_bancaria_asociada.id_moneda,
                        id_moneda_base=self.id_cuenta_bancaria_asociada.id_moneda,  # Asumir misma moneda por simplicidad
                        monto_base_empresa=comision,
                        id_metodo_pago=metodo_comision,
                        descripcion=f"Comisión bancaria datafono {self.nombre} - Cierre {self.serial}",
                        tipo_documento_asociado="GASTO",
                        nro_documento_asociado=f"Cierre {self.serial}",
                        id_cuenta_bancaria=self.id_cuenta_bancaria_asociada,
                        id_usuario_registro=usuario if usuario else None,
                    )

            # Actualizar saldo de la cuenta bancaria
            self.id_cuenta_bancaria_asociada.saldo_actual += neto
            self.id_cuenta_bancaria_asociada.save()
            # Marcar transacciones como conciliadas
            transacciones.update(conciliada=True)
            # Resetear saldo temporal y actualizar fecha de cierre
            self.saldo_temporal = Decimal("0.00")
            self.fecha_ultimo_cierre = limite
            self.save()
        return {
            "total": total,
            "comision": comision,
            "neto": neto,
            "movimiento_id": movimiento.id_movimiento,
            "transacciones_conciliadas": transacciones.count(),
            "fecha_cierre": limite,
            "mensaje": "Cierre realizado correctamente.",
        }

    id_datafono = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="datafonos")
    id_sucursal = models.ForeignKey("core.Sucursal", on_delete=models.CASCADE, related_name="datafonos")
    # Campo eliminado: id_caja - ahora solo se asocia a caja física
    # id_caja = models.ForeignKey('Caja', on_delete=models.SET_NULL, null=True, blank=True, related_name='datafonos_caja_virtual', help_text="Caja principal a la que está asociado el datafono.")
    id_caja_fisica = models.ForeignKey(
        "CajaFisica",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="datafonos",
        help_text="Caja física donde está conectado el datafono.",
    )
    nombre = models.CharField(max_length=100)
    serial = models.CharField(
        max_length=100, unique=True, help_text="Número de serie o identificación única del datafono."
    )
    id_cuenta_bancaria_asociada = models.ForeignKey(
        "CuentaBancariaEmpresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="datafonos",
        help_text="Cuenta bancaria donde se depositan los fondos.",
    )
    comision_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00, help_text="Porcentaje de comisión por transacción."
    )
    saldo_temporal = models.DecimalField(
        max_digits=18, decimal_places=2, default=0.00, help_text="Saldo acumulado de transacciones no cerradas."
    )
    fecha_ultimo_cierre = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # Métodos de pago y monedas aceptadas
    metodos_pago = models.ManyToManyField(
        "MetodoPago", related_name="datafonos", blank=True, help_text="Métodos de pago permitidos para este datafono."
    )
    monedas = models.ManyToManyField(
        "Moneda", related_name="datafonos", blank=True, help_text="Monedas aceptadas por este datafono."
    )

    class Meta:
        db_table = "finanzas_datafono"
        verbose_name = "Datafono"
        verbose_name_plural = "Datafonos"

    def __str__(self):
        return f"{self.nombre} - {self.serial}"


class SesionDatafono(models.Model):
    ESTADOS = [
        ("ABIERTA", "Abierta"),
        ("CERRADA", "Cerrada"),
        ("CONCILIADA", "Conciliada"),
    ]

    id_sesion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    datafono = models.ForeignKey("Datafono", on_delete=models.CASCADE, related_name="sesiones")
    usuario_apertura = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, related_name="sesiones_datafono_abiertas"
    )
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="ABIERTA")

    # Totales acumulados
    total_transacciones = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    comision_calculada = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    neto_esperado = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)

    # Metadata
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "finanzas_sesion_datafono"
        verbose_name = "Sesión de Datafono"
        verbose_name_plural = "Sesiones de Datafonos"
        ordering = ["-fecha_apertura"]

    def __str__(self):
        return f"Sesión {self.datafono.nombre} - {self.fecha_apertura.strftime('%Y-%m-%d %H:%M')}"

    def cerrar_sesion(self, usuario_cierre=None):
        """
        Cierra la sesión del datafono y calcula los totales finales.
        """
        from decimal import Decimal

        from django.utils import timezone

        if self.estado != "ABIERTA":
            raise ValueError("La sesión ya está cerrada")

        # Calcular totales basados en transacciones pendientes
        transacciones_pendientes = self.transacciones_datafono.filter(estado="PENDIENTE")
        total_adicional = sum((t.monto for t in transacciones_pendientes), Decimal("0.00"))

        self.total_transacciones += total_adicional
        self.comision_calculada = self.total_transacciones * (self.datafono.comision_porcentaje / Decimal("100"))
        self.neto_esperado = self.total_transacciones - self.comision_calculada
        self.fecha_cierre = timezone.now()
        self.estado = "CERRADA"
        self.save()

        # Marcar transacciones como cerradas
        transacciones_pendientes.update(estado="CERRADO_EN_DATAFONO")

        return self


class TransaccionDatafono(models.Model):
    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("CERRADO_EN_DATAFONO", "Cerrado en Datafono"),
        ("ENVIADO_A_BANCO", "Enviado a Banco"),
        ("CONCILIADO", "Conciliado"),
    ]

    id_transaccion_datafono = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_datafono = models.ForeignKey("Datafono", on_delete=models.CASCADE, related_name="transacciones_datafono")
    sesion_datafono = models.ForeignKey(
        "SesionDatafono", on_delete=models.CASCADE, null=True, blank=True, related_name="transacciones_datafono"
    )
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    referencia_bancaria = models.CharField(
        max_length=100, null=True, blank=True, help_text="Número de referencia de la operación en el datafono."
    )

    # Estados de la transacción
    estado = models.CharField(max_length=20, choices=ESTADOS, default="PENDIENTE")
    lote_bancario = models.CharField(
        max_length=50, null=True, blank=True, help_text="ID del lote bancario al que pertenece esta transacción"
    )

    # Fechas de tracking
    fecha_hora_transaccion = models.DateTimeField(auto_now_add=True)
    fecha_envio_banco = models.DateTimeField(null=True, blank=True)
    fecha_conciliacion = models.DateTimeField(null=True, blank=True)

    # Campos legacy (mantener compatibilidad)
    conciliada = models.BooleanField(default=False, help_text="Campo legacy - usar estado='CONCILIADO' en su lugar.")

    # Relaciones
    id_transaccion_financiera_origen = models.ForeignKey(
        "TransaccionFinanciera",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transacciones_datafono",
        help_text="Transacción de venta que originó el pago con datafono.",
    )
    id_usuario_registro = models.ForeignKey("core.Usuarios", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "finanzas_transaccion_datafono"
        verbose_name = "Transacción de Datafono"
        verbose_name_plural = "Transacciones de Datafonos"

    def __str__(self):
        return f"Transacción en {self.id_datafono.nombre} - {self.monto} ({self.get_estado_display()})"


class DepositoDatafono(models.Model):
    ESTADOS = [
        ("PENDIENTE", "Pendiente de Recepción"),
        ("RECIBIDO", "Recibido en Banco"),
        ("CONCILIADO", "Conciliado"),
    ]

    id_deposito = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    datafono = models.ForeignKey("Datafono", on_delete=models.CASCADE, related_name="depositos")
    sesion_datafono = models.ForeignKey("SesionDatafono", on_delete=models.CASCADE, related_name="depositos")

    # Identificación del lote
    lote_bancario = models.CharField(
        max_length=50, unique=True, help_text="Identificador único del lote enviado al banco"
    )

    # Fechas
    fecha_envio = models.DateTimeField(help_text="Fecha y hora en que se envió el depósito al banco")
    fecha_recepcion_banco = models.DateTimeField(
        null=True, blank=True, help_text="Fecha y hora en que el banco recibió el depósito"
    )
    fecha_conciliacion = models.DateTimeField(
        null=True, blank=True, help_text="Fecha y hora en que se concilió el depósito"
    )

    # Estado
    estado = models.CharField(max_length=20, choices=ESTADOS, default="PENDIENTE")

    # Montos
    total_bruto = models.DecimalField(
        max_digits=18, decimal_places=2, help_text="Total de transacciones antes de comisión"
    )
    comision_banco = models.DecimalField(max_digits=18, decimal_places=2, help_text="Comisión calculada por el banco")
    total_neto = models.DecimalField(
        max_digits=18, decimal_places=2, help_text="Monto neto recibido (bruto - comisión)"
    )

    # Referencias bancarias
    referencia_banco = models.CharField(
        max_length=100, null=True, blank=True, help_text="Referencia proporcionada por el banco"
    )
    movimiento_banco = models.OneToOneField(
        "MovimientoCajaBanco", on_delete=models.SET_NULL, null=True, blank=True, related_name="deposito_datafono"
    )

    # Metadata
    usuario_envio = models.ForeignKey(
        "core.Usuarios", on_delete=models.SET_NULL, null=True, blank=True, related_name="depositos_enviados"
    )
    usuario_conciliacion = models.ForeignKey(
        "core.Usuarios", on_delete=models.SET_NULL, null=True, blank=True, related_name="depositos_conciliados"
    )
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "finanzas_deposito_datafono"
        verbose_name = "Depósito de Datafono"
        verbose_name_plural = "Depósitos de Datafonos"
        ordering = ["-fecha_envio"]

    def __str__(self):
        return f"Depósito {self.lote_bancario} - {self.datafono.nombre} - {self.total_neto}"

    def conciliar(self, movimiento_banco, usuario):
        """
        Conciliar este depósito con un movimiento bancario recibido.
        """
        from django.utils import timezone

        if self.estado == "CONCILIADO":
            raise ValueError("El depósito ya está conciliado")

        # Actualizar estado y referencias
        self.estado = "CONCILIADO"
        self.movimiento_banco = movimiento_banco
        self.fecha_conciliacion = timezone.now()
        self.usuario_conciliacion = usuario
        self.save()

        # Actualizar sesión
        self.sesion_datafono.estado = "CONCILIADA"
        self.sesion_datafono.save()

        # Marcar transacciones como conciliadas
        self.sesion_datafono.transacciones_datafono.filter(
            estado__in=["ENVIADO_A_BANCO", "CERRADO_EN_DATAFONO"]
        ).update(estado="CONCILIADO", fecha_conciliacion=self.fecha_conciliacion)

        return self


class MovimientoCajaBanco(models.Model):
    TIPOS_MOVIMIENTO = [
        ("INGRESO", "Ingreso"),
        ("EGRESO", "Egreso"),
        ("TRANSFERENCIA_ENTRADA", "Transferencia Entrada"),
        ("TRANSFERENCIA_SALIDA", "Transferencia Salida"),
        ("AJUSTE_POSITIVO", "Ajuste Positivo"),
        ("AJUSTE_NEGATIVO", "Ajuste Negativo"),
        # Corte de cierre de caja física: monto 0, saldo_nuevo = saldo real
        # contado. Es el registro persistente del que CajaFisica.realizar_cierre
        # re-deriva la ventana y el saldo base del siguiente cierre.
        ("CIERRE", "Cierre"),
    ]

    id_movimiento = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="movimientos_caja_banco")
    fecha_movimiento = models.DateField()
    hora_movimiento = models.TimeField()
    tipo_movimiento = models.CharField(max_length=50, choices=TIPOS_MOVIMIENTO)
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    id_moneda = models.ForeignKey(
        "Moneda", on_delete=models.CASCADE, related_name="movimientos_caja_banco", null=True, blank=True
    )
    concepto = models.CharField(max_length=255)
    referencia = models.CharField(max_length=100, null=True, blank=True)
    id_caja = models.ForeignKey(
        "Caja",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="movimientos",
        help_text="Referencia a caja virtual",
    )
    id_caja_fisica = models.ForeignKey(
        "CajaFisica",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="movimientos",
        help_text="Referencia a caja física",
    )
    id_cuenta_bancaria = models.ForeignKey(
        "CuentaBancariaEmpresa", on_delete=models.CASCADE, null=True, blank=True, related_name="movimientos"
    )
    id_transaccion_financiera = models.ForeignKey(
        "TransaccionFinanciera", on_delete=models.CASCADE, null=True, blank=True, related_name="movimientos_caja_banco"
    )
    saldo_anterior = models.DecimalField(max_digits=18, decimal_places=2)
    saldo_nuevo = models.DecimalField(max_digits=18, decimal_places=2)
    id_usuario_registro = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, related_name="movimientos_caja_banco_registrados"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finanzas_movimiento_caja_banco"
        verbose_name = "Movimiento de Caja/Banco"
        verbose_name_plural = "Movimientos de Caja/Banco"

    def __str__(self):
        return f"{self.tipo_movimiento} - {self.monto} ({self.fecha_movimiento})"


# Modelo para sesiones activas de cajas físicas
class SesionCajaFisica(models.Model):
    ESTADO_SESION_CHOICES = [
        ("ABIERTA", "Abierta"),
        ("CERRADA", "Cerrada"),
        ("PAUSADA", "Pausada"),
    ]

    id_sesion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    caja_fisica = models.ForeignKey("CajaFisica", on_delete=models.CASCADE, related_name="sesiones")
    usuario = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE, related_name="sesiones_caja_fisica")
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="sesiones_caja_fisica")
    sucursal = models.ForeignKey(
        "core.Sucursal", on_delete=models.SET_NULL, null=True, blank=True, related_name="sesiones_caja_fisica"
    )

    # Estado y timestamps
    estado = models.CharField(max_length=20, choices=ESTADO_SESION_CHOICES, default="ABIERTA")
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    fecha_ultima_actividad = models.DateTimeField(auto_now=True)

    # Información adicional
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    notas = models.TextField(null=True, blank=True)

    # Saldo al abrir la sesión
    saldo_inicial = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)

    class Meta:
        db_table = "finanzas_sesion_caja_fisica"
        verbose_name = "Sesión de Caja Física"
        verbose_name_plural = "Sesiones de Caja Física"
        ordering = ["-fecha_apertura"]
        constraints = [
            # Solo una sesión ABIERTA por caja física a la vez
            models.UniqueConstraint(
                fields=["caja_fisica"], condition=models.Q(estado="ABIERTA"), name="unique_sesion_abierta_por_caja"
            )
        ]

    def __str__(self):
        return f"Sesión {self.caja_fisica.nombre} - {self.usuario.username} ({self.get_estado_display()})"

    @property
    def esta_activa(self):
        """Retorna True si la sesión está abierta"""
        return self.estado == "ABIERTA"

    @property
    def duracion(self):
        """Retorna la duración de la sesión en minutos"""
        if self.fecha_cierre:
            return (self.fecha_cierre - self.fecha_apertura).total_seconds() / 60
        return (timezone.now() - self.fecha_apertura).total_seconds() / 60

    def cerrar_sesion(self, notas_cierre=None, saldos_reales=None, usuario=None, hasta=None):
        """
        Cierra la sesión de caja de forma ATÓMICA.

        FIX (endpoint roto): la vista llamaba este método con
        ``saldos_reales/usuario/hasta`` pero la firma solo aceptaba
        ``notas_cierre`` → TypeError 500. Ahora, si se pasa ``saldos_reales``
        (dict {id_caja: saldo_real_contado}), se realiza el cierre de cada
        caja de la sesión — la caja física principal y/o sus cajas virtuales
        asociadas — reutilizando el corte persistente del PR #73
        (``services.realizar_cierre_caja``), y se marca la sesión CERRADA en
        la misma transacción.

        Args:
            notas_cierre:  Notas a guardar en la sesión (opcional).
            saldos_reales: dict {id_caja (str/UUID): saldo real contado}.
                           Las claves deben ser la caja física de la sesión o
                           una de sus cajas virtuales; otra cosa → ValueError.
            usuario:       Usuario que cierra (para los movimientos de cierre).
            hasta:         datetime límite de los cierres (opcional).

        Returns:
            dict {id_caja: resumen del cierre} (vacío si no se pidieron cierres).

        Raises:
            ValueError con mensaje de negocio (sesión ya cerrada, caja ajena a
            la sesión, saldo no numérico, límite anterior al último cierre).
        """
        from decimal import Decimal, InvalidOperation

        from django.db import transaction
        from django.utils import timezone

        from .services import realizar_cierre_caja

        cierres = {}
        with transaction.atomic():
            # Lock de la sesión: serializa cierres concurrentes y fija el
            # estado leído (no cerrar dos veces / no cerrar sobre cerrada).
            sesion = type(self).objects.select_for_update().get(pk=self.pk)
            if sesion.estado == "CERRADA":
                raise ValueError("La sesión ya está cerrada.")

            for caja_id, saldo in (saldos_reales or {}).items():
                caja = self._resolver_caja_de_sesion(caja_id)
                try:
                    # R-CODE-4: nunca Decimal(float) — pasar por str.
                    saldo_decimal = Decimal(str(saldo))
                except (InvalidOperation, ValueError, TypeError):
                    raise ValueError(f"El saldo_real enviado para la caja {caja_id} no es un número válido.")
                cierres[str(caja_id)] = realizar_cierre_caja(
                    caja, saldo_decimal, usuario=usuario, hasta=hasta
                )

            self.estado = "CERRADA"
            self.fecha_cierre = timezone.now()
            if notas_cierre:
                self.notas = notas_cierre
            self.save()
        return cierres

    def _resolver_caja_de_sesion(self, caja_id):
        """
        Resuelve una caja perteneciente a la sesión: la caja física principal
        o una de sus cajas virtuales asociadas. Cualquier otra cosa →
        ValueError (no se filtra existencia de cajas ajenas).
        """
        if str(caja_id) == str(self.caja_fisica_id):
            return self.caja_fisica
        try:
            return self.caja_fisica.cajas_virtuales.get(id_caja=caja_id)
        except (Caja.DoesNotExist, ValueError, TypeError, ValidationError):
            raise ValueError(f"La caja {caja_id} no pertenece a esta sesión.")

    @classmethod
    def obtener_sesion_activa(cls, caja_fisica, usuario=None):
        """Obtiene la sesión activa para una caja física (opcionalmente filtrada por usuario)"""
        queryset = cls.objects.filter(caja_fisica=caja_fisica, estado="ABIERTA")
        if usuario:
            queryset = queryset.filter(usuario=usuario)
        return queryset.first()

    @classmethod
    def abrir_sesion(cls, caja_fisica, usuario, ip_address=None, user_agent=None):
        """Abre una nueva sesión para una caja física"""
        from django.db import transaction

        with transaction.atomic():
            # Cerrar cualquier sesión anterior abierta para esta caja
            sesiones_anteriores = cls.objects.filter(caja_fisica=caja_fisica, estado="ABIERTA")
            for sesion in sesiones_anteriores:
                sesion.cerrar_sesion("Sesión cerrada automáticamente por nueva apertura")

            # Verificar nuevamente que no queden sesiones abiertas (por si acaso)
            sesiones_abiertas = cls.objects.filter(caja_fisica=caja_fisica, estado="ABIERTA")
            if sesiones_abiertas.exists():
                # Si aún quedan sesiones abiertas, forzar el cierre
                sesiones_abiertas.update(
                    estado="CERRADA",
                    fecha_cierre=timezone.now(),
                    notas="Sesión cerrada automáticamente por nueva apertura (forzado)",
                )

            # Crear nueva sesión
            return cls.objects.create(
                caja_fisica=caja_fisica,
                usuario=usuario,
                empresa=caja_fisica.empresa,
                sucursal=caja_fisica.sucursal,
                ip_address=ip_address,
                user_agent=user_agent,
                saldo_inicial=caja_fisica.saldo_actual if hasattr(caja_fisica, "saldo_actual") else 0.00,
            )


# --- SINCRONIZACIÓN Y VALIDACIÓN MULTI-TENANT ---


def sync_moneda_empresa_activa(moneda):
    """
    Sincroniza la moneda en MonedaEmpresaActiva para todas las empresas que deben verla.
    """
    from apps.core.models import Empresa

    if moneda.es_generica or moneda.es_publica:
        empresas = Empresa.objects.all()
        for empresa in empresas:
            MonedaEmpresaActiva.objects.get_or_create(empresa=empresa, moneda=moneda, defaults={"activa": True})
    elif moneda.empresa:
        MonedaEmpresaActiva.objects.get_or_create(empresa=moneda.empresa, moneda=moneda, defaults={"activa": True})


@receiver(post_save, sender=Moneda)
def moneda_post_save(sender, instance, created, **kwargs):
    sync_moneda_empresa_activa(instance)


@receiver(post_save, sender=MetodoPago)
def metodopago_post_save(sender, instance, created, **kwargs):
    from apps.core.models import Empresa

    if instance.es_generico or instance.es_publico:
        empresas = Empresa.objects.all()
        for empresa in empresas:
            MetodoPagoEmpresaActiva.objects.get_or_create(
                empresa=empresa, metodo_pago=instance, defaults={"activa": True}
            )
    elif instance.empresa:
        MetodoPagoEmpresaActiva.objects.get_or_create(
            empresa=instance.empresa, metodo_pago=instance, defaults={"activa": True}
        )


# --- VALIDACIÓN EN EL MODELO METODOPAGO ---
from django.core.exceptions import ValidationError


def validar_monedas_metodopago(metodopago, monedas):
    # Efectivo y Cheque: solo fiat, nunca crypto ni otro tipo
    if metodopago.tipo_metodo in ["EFECTIVO", "CHEQUE"]:
        for moneda in monedas:
            if moneda.tipo_moneda != "fiat":
                raise ValidationError(
                    f"No se puede asociar la moneda {moneda.nombre} ({moneda.codigo_iso}) a '{metodopago.tipo_metodo}'. Solo monedas fiat están permitidas."
                )


# Sobrescribe save() en MetodoPago para validar y sincronizar
old_metodopago_save = MetodoPago.save


def metodopago_save(self, *args, **kwargs):
    super(MetodoPago, self).save(*args, **kwargs)  # Guardar primero para tener ID
    monedas = list(self.monedas.all())
    validar_monedas_metodopago(self, monedas)
    # Sincroniza activos por empresa
    metodopago_post_save(MetodoPago, self, created=False)


MetodoPago.save = metodopago_save

# Sobrescribe save() en Moneda para sincronizar activos
old_moneda_save = Moneda.save


def moneda_save(self, *args, **kwargs):
    super(Moneda, self).save(*args, **kwargs)
    sync_moneda_empresa_activa(self)


Moneda.save = moneda_save


class PlantillaMaestroCajasVirtuales(models.Model):
    """
    Plantilla maestra que define las cajas virtuales para toda la empresa.
    Se aplica automáticamente a todas las cajas físicas y empleados autorizados.
    """

    id_plantilla_maestro = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="plantilla_maestro_cajas")

    nombre = models.CharField(max_length=100, help_text="Nombre de la configuración maestra")
    descripcion = models.TextField(blank=True, null=True)

    # Configuración que se aplica a TODAS las cajas virtuales del tipo
    moneda_base = models.ForeignKey("Moneda", on_delete=models.CASCADE, related_name="plantillas_maestro_monedas")
    metodos_pago_base = models.ManyToManyField(
        "MetodoPago",
        related_name="plantillas_maestro_metodos",
        help_text="Métodos de pago disponibles en la plantilla",
    )

    # Control de aplicación automática
    aplicar_a_todas_cajas_fisicas = models.BooleanField(
        default=True, help_text="Si es True, se aplica automáticamente a todas las cajas físicas"
    )
    aplicar_a_empleados_con_rol = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Nombre del rol/permiso para aplicar automáticamente a empleados",
    )

    activa = models.BooleanField(default=True)
    creada_por = models.ForeignKey("core.Usuarios", on_delete=models.SET_NULL, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "finanzas_plantilla_maestro_cajas"
        verbose_name = "Plantilla Maestro Cajas Virtuales"
        verbose_name_plural = "Plantillas Maestro Cajas Virtuales"

    def __str__(self):
        return f"Plantilla Maestro: {self.nombre} ({self.empresa})"

    def sincronizar_cajas_virtuales(self):
        """
        Sincroniza todas las cajas virtuales basadas en esta plantilla.
        Se ejecuta cuando cambia la plantilla.
        """
        from .models import CajaVirtualAuto

        # Obtener todas las cajas virtuales basadas en esta plantilla
        cajas_virtuales = CajaVirtualAuto.objects.filter(plantilla_maestro=self)

        for caja_virtual in cajas_virtuales:
            caja_virtual.sincronizar_con_plantilla()
            caja_virtual.save()

    def crear_cajas_para_caja_fisica(self, caja_fisica):
        """
        Crea las cajas virtuales automáticas para una caja física específica.
        """
        from .models import CajaVirtualAuto

        # Crear cajas virtuales basadas en esta plantilla
        cajas_creadas = []

        # Combinaciones de monedas y métodos de pago
        for metodo_pago in self.metodos_pago_base.all():
            # Verificar si no está deshabilitado específicamente para esta caja
            if not caja_fisica.metodo_pago_deshabilitado(metodo_pago):
                caja_virtual, created = CajaVirtualAuto.objects.get_or_create(
                    caja_fisica=caja_fisica,
                    plantilla_maestro=self,
                    moneda=self.moneda_base,
                    metodo_pago=metodo_pago,
                    defaults={"activa": True, "creada_automaticamente": True},
                )
                if created:
                    cajas_creadas.append(caja_virtual)

        return cajas_creadas

    def crear_cajas_para_empleado(self, empleado):
        """
        Crea las cajas virtuales automáticas para un empleado específico.
        """
        from .models import CajaVirtualAuto

        # Crear cajas virtuales basadas en esta plantilla para el empleado
        cajas_creadas = []

        # Solo si el empleado tiene el rol especificado
        if self.aplicar_a_empleados_con_rol and hasattr(empleado, "groups"):
            if empleado.groups.filter(name=self.aplicar_a_empleados_con_rol).exists():
                # Para empleados móviles, crear cajas virtuales sin caja física asociada
                for metodo_pago in self.metodos_pago_base.all():
                    caja_virtual, created = CajaVirtualAuto.objects.get_or_create(
                        empleado=empleado,
                        plantilla_maestro=self,
                        moneda=self.moneda_base,
                        metodo_pago=metodo_pago,
                        defaults={"activa": True, "creada_automaticamente": True},
                    )
                    if created:
                        cajas_creadas.append(caja_virtual)

        return cajas_creadas


class CajaVirtualAuto(models.Model):
    """
    Cajas virtuales automáticas creadas desde plantillas maestras.
    Se mantienen sincronizadas automáticamente con sus plantillas.
    """

    id_caja_virtual = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    # Asociación: puede ser con caja física O con empleado (para vendedores móviles)
    # FIX: el FK apuntaba a Caja (virtual) en vez de CajaFisica — modelado roto.
    caja_fisica = models.ForeignKey(
        "CajaFisica", on_delete=models.CASCADE, null=True, blank=True, related_name="cajas_virtuales_auto"
    )
    empleado = models.ForeignKey(
        "core.Usuarios", on_delete=models.CASCADE, null=True, blank=True, related_name="cajas_virtuales_auto"
    )

    # Plantilla que la controla
    plantilla_maestro = models.ForeignKey(
        "PlantillaMaestroCajasVirtuales", on_delete=models.CASCADE, related_name="cajas_virtuales_auto"
    )

    # Configuración específica (heredada de plantilla pero puede ser overrideada)
    moneda = models.ForeignKey("Moneda", on_delete=models.CASCADE)
    metodo_pago = models.ForeignKey("MetodoPago", on_delete=models.CASCADE)

    # Control
    activa = models.BooleanField(default=True)
    creada_automaticamente = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "finanzas_caja_virtual_auto"
        verbose_name = "Caja Virtual Automática"
        verbose_name_plural = "Cajas Virtuales Automáticas"
        unique_together = [
            ("caja_fisica", "plantilla_maestro", "moneda", "metodo_pago"),
            ("empleado", "plantilla_maestro", "moneda", "metodo_pago"),
        ]

    def __str__(self):
        tipo = "Física" if self.caja_fisica else "Empleado"
        entidad = str(self.caja_fisica) if self.caja_fisica else str(self.empleado)
        return f"{self.plantilla_maestro.nombre} - {entidad} ({self.moneda.codigo_iso} - {self.metodo_pago.nombre_metodo})"

    def sincronizar_con_plantilla(self):
        """
        Sincroniza esta caja virtual con los cambios en su plantilla maestra.
        """
        plantilla = self.plantilla_maestro

        # Verificar si la moneda y método siguen siendo válidos
        moneda_valida = plantilla.moneda_base == self.moneda
        metodo_valido = plantilla.metodos_pago_base.filter(id_metodo_pago=self.metodo_pago.id_metodo_pago).exists()

        # Verificar si está deshabilitado específicamente para esta caja física
        deshabilitado = False
        if self.caja_fisica:
            deshabilitado = self.caja_fisica.metodo_pago_deshabilitado(self.metodo_pago)

        # Actualizar estado
        self.activa = plantilla.activa and moneda_valida and metodo_valido and not deshabilitado
        self.save()

    def crear_caja_virtual_en_sesion(self, sesion):
        """
        Crea una caja virtual temporal en la sesión basada en esta configuración automática.
        """
        return sesion.crear_caja_virtual(
            nombre=f"{self.plantilla_maestro.nombre} - {self.moneda.codigo_iso} {self.metodo_pago.nombre_metodo}",
            monedas_ids=[str(self.moneda.id_moneda)],
            metodos_pago_ids=[str(self.metodo_pago.id_metodo_pago)],
            usuario=sesion.usuario,
        )


class CajaMetodoPagoOverride(models.Model):
    """
    Override para deshabilitar métodos de pago específicos en cajas físicas o sucursales.
    Anula las configuraciones de las plantillas maestras.
    """

    id_override = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    caja_fisica = models.ForeignKey("CajaFisica", on_delete=models.CASCADE, related_name="metodo_pago_overrides")
    metodo_pago = models.ForeignKey("MetodoPago", on_delete=models.CASCADE, related_name="caja_overrides")
    sucursal = models.ForeignKey("core.Sucursal", on_delete=models.CASCADE, related_name="metodo_pago_overrides")

    deshabilitado = models.BooleanField(
        default=True, help_text="Si es True, este método de pago queda deshabilitado para esta caja/sucursal"
    )
    motivo = models.TextField(null=True, blank=True, help_text="Motivo del override")

    creado_por = models.ForeignKey(
        "core.Usuarios", on_delete=models.SET_NULL, null=True, blank=True, related_name="metodo_pago_overrides"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finanzas_caja_metodo_pago_override"
        verbose_name = "Override Método de Pago"
        verbose_name_plural = "Overrides Métodos de Pago"
        unique_together = ["caja_fisica", "metodo_pago", "sucursal"]

    def __str__(self):
        return f"Override {self.metodo_pago.nombre_metodo} en {self.caja_fisica.nombre} - {'Deshabilitado' if self.deshabilitado else 'Habilitado'}"


# --- SEÑALES PARA SINCRONIZACIÓN AUTOMÁTICA ---


@receiver(post_save, sender="finanzas.PlantillaMaestroCajasVirtuales")
def plantilla_maestro_post_save(sender, instance, created, **kwargs):
    """
    Cuando se crea/modifica una plantilla maestra, sincronizar todas las cajas virtuales y crear en cajas físicas existentes si es nueva.
    """
    if created:
        # Para plantillas nuevas, crear cajas virtuales en todas las cajas físicas existentes
        from .models import Caja, CajaFisica

        cajas_fisicas = CajaFisica.objects.filter(empresa=instance.empresa, activa=True)
        for caja_fisica in cajas_fisicas:
            # Verificar si ya existe una caja virtual con la misma moneda y métodos de pago
            metodos_plantilla = set(instance.metodos_pago_base.all())
            caja_existente = Caja.objects.filter(
                caja_fisica=caja_fisica, moneda=instance.moneda_base, activa=True
            ).first()
            if caja_existente:
                metodos_existentes = set(caja_existente.metodos_pago.all())
                if metodos_existentes == metodos_plantilla:
                    continue  # Ya existe, no crear
            # Crear la caja virtual
            caja_virtual, created_caja = Caja.objects.get_or_create(
                caja_fisica=caja_fisica,
                plantilla_maestro=instance,
                moneda=instance.moneda_base,
                defaults={
                    "empresa": caja_fisica.empresa,
                    "sucursal": caja_fisica.sucursal,
                    "nombre": f"{instance.nombre} - {caja_fisica.nombre}",
                    "tipo_caja": caja_fisica.tipo_caja,
                    "descripcion": instance.descripcion,
                    "activa": True,
                },
            )
            if created_caja:
                caja_virtual.metodos_pago.set(instance.metodos_pago_base.all())
                caja_virtual.save()
    else:
        # Para actualizaciones, sincronizar existentes
        instance.sincronizar_cajas_virtuales()


@receiver(post_save, sender="core.Usuarios")
def usuario_post_save(sender, instance, created, **kwargs):
    """
    Cuando se crea un nuevo usuario, asignar automáticamente cajas virtuales si tiene el rol correspondiente.
    """
    if created:
        # Buscar plantillas maestras que apliquen a empleados con ciertos roles
        plantillas_maestro = PlantillaMaestroCajasVirtuales.objects.filter(
            empresa__in=instance.empresas.all(), activa=True, aplicar_a_empleados_con_rol__isnull=False
        )

        for plantilla in plantillas_maestro:
            plantilla.crear_cajas_para_empleado(instance)


@receiver(post_save, sender="finanzas.CajaMetodoPagoOverride")
def override_post_save(sender, instance, created, **kwargs):
    """
    Cuando se crea/modifica un override, sincronizar las cajas virtuales afectadas.
    """
    # Sincronizar todas las cajas virtuales de esta caja física
    from .models import CajaVirtualAuto

    cajas_virtuales = CajaVirtualAuto.objects.filter(caja_fisica=instance.caja_fisica)
    for caja_virtual in cajas_virtuales:
        caja_virtual.sincronizar_con_plantilla()


@receiver(post_save, sender=CajaFisica)
def crear_cajas_virtuales_automaticas(sender, instance, created, **kwargs):
    if created and instance.empresa:
        from .models import Caja, PlantillaMaestroCajasVirtuales

        plantillas = PlantillaMaestroCajasVirtuales.objects.filter(empresa=instance.empresa, activa=True)
        for plantilla in plantillas:
            # Verificar si ya existe una caja virtual con la misma moneda y métodos de pago en esta caja física
            metodos_plantilla = set(plantilla.metodos_pago_base.all())
            caja_existente = Caja.objects.filter(
                caja_fisica=instance, moneda=plantilla.moneda_base, activa=True
            ).first()
            if caja_existente:
                metodos_existentes = set(caja_existente.metodos_pago.all())
                if metodos_existentes == metodos_plantilla:
                    continue  # Ya existe una caja virtual con la misma configuración, no crear
            # Crear la caja virtual si no existe
            caja_virtual, created_caja = Caja.objects.get_or_create(
                caja_fisica=instance,
                plantilla_maestro=plantilla,
                moneda=plantilla.moneda_base,
                defaults={
                    "empresa": instance.empresa,
                    "sucursal": instance.sucursal,
                    "nombre": f"{plantilla.nombre} - {instance.nombre}",
                    "tipo_caja": instance.tipo_caja,
                    "descripcion": plantilla.descripcion,
                    "activa": True,
                },
            )
            if created_caja:
                caja_virtual.metodos_pago.set(plantilla.metodos_pago_base.all())
                caja_virtual.save()


# Funciones para manejo del flujo de pagos con datafono


def registrar_pago_tarjeta(datafono, monto, referencia, transaccion_financiera, usuario):
    """
    Registra un pago con tarjeta en el datafono.
    Crea o reutiliza una sesión abierta del datafono.
    """
    from decimal import Decimal

    from django.utils import timezone

    # Obtener o crear sesión abierta
    sesion, created = SesionDatafono.objects.get_or_create(
        datafono=datafono,
        estado="ABIERTA",
        defaults={
            "usuario_apertura": usuario,
        },
    )

    # Crear transacción
    transaccion = TransaccionDatafono.objects.create(
        id_datafono=datafono,
        sesion_datafono=sesion,
        monto=monto,
        referencia_bancaria=referencia,
        estado="PENDIENTE",
        id_transaccion_financiera_origen=transaccion_financiera,
        id_usuario_registro=usuario,
    )

    # Actualizar totales de la sesión
    sesion.total_transacciones += Decimal(str(monto))
    sesion.save()

    return transaccion


def cerrar_sesion_datafono(datafono, usuario_cierre):
    """
    Cierra la sesión abierta del datafono y crea un depósito consolidado.
    """
    from decimal import Decimal

    from django.utils import timezone

    # Obtener sesión abierta
    try:
        sesion = SesionDatafono.objects.get(datafono=datafono, estado="ABIERTA")
    except SesionDatafono.DoesNotExist:
        raise ValueError("No hay sesión abierta para este datafono")

    # Cerrar la sesión
    sesion.cerrar_sesion()

    # Crear depósito consolidado
    lote_id = f"{datafono.serial}_{sesion.fecha_cierre.strftime('%Y%m%d_%H%M%S')}"

    deposito = DepositoDatafono.objects.create(
        datafono=datafono,
        sesion_datafono=sesion,
        lote_bancario=lote_id,
        fecha_envio=sesion.fecha_cierre,
        total_bruto=sesion.total_transacciones,
        comision_banco=sesion.comision_calculada,
        total_neto=sesion.neto_esperado,
        usuario_envio=usuario_cierre,
    )

    # Actualizar transacciones con el lote bancario
    sesion.transacciones_datafono.filter(estado="CERRADO_EN_DATAFONO").update(
        estado="ENVIADO_A_BANCO", lote_bancario=lote_id, fecha_envio_banco=sesion.fecha_cierre
    )

    return deposito


def conciliar_deposito_datafono(deposito, movimiento_banco, usuario):
    """
    Conciliar un depósito de datafono con un movimiento bancario recibido.
    """
    return deposito.conciliar(movimiento_banco, usuario)


def obtener_sesion_activa_datafono(datafono):
    """
    Obtiene la sesión activa de un datafono, o None si no hay ninguna.
    """
    try:
        return SesionDatafono.objects.get(datafono=datafono, estado="ABIERTA")
    except SesionDatafono.DoesNotExist:
        return None


def obtener_depositos_pendientes(datafono=None):
    """
    Obtiene los depósitos pendientes de conciliación.
    Si se especifica datafono, filtra por ese datafono.
    """
    queryset = DepositoDatafono.objects.filter(estado__in=["PENDIENTE", "RECIBIDO"])
    if datafono:
        queryset = queryset.filter(datafono=datafono)
    return queryset.order_by("-fecha_envio")


# Modelo genérico unificado para todos los tipos de pagos (ingresos y egresos)
class Pago(models.Model):
    TIPO_OPERACION_CHOICES = [
        ("INGRESO", "Ingreso"),
        ("EGRESO", "Egreso"),
    ]

    TIPO_DOCUMENTO_CHOICES = [
        ("PEDIDO", "Pedido de Venta"),
        ("FACTURA", "Factura Fiscal"),
        ("NOTA_VENTA", "Nota de Venta"),
        ("NOTA_CREDITO_VENTA", "Nota de Crédito Venta"),
        ("CXP", "Cuenta por Pagar"),
        ("COMPRA", "Compra"),
        ("GASTO", "Gasto"),
        ("REEMBOLSO_GASTO", "Reembolso de Gasto"),
        ("NOMINA", "Nómina"),
        ("IMPUESTO", "Impuesto/Contribución"),
        ("AJUSTE", "Ajuste Manual"),
        ("TRANSFERENCIA", "Transferencia"),
    ]

    # Campos básicos
    id_pago = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="pagos")

    # Clasificación del pago
    tipo_operacion = models.CharField(max_length=20, choices=TIPO_OPERACION_CHOICES)
    tipo_documento = models.CharField(max_length=30, choices=TIPO_DOCUMENTO_CHOICES)
    id_documento = models.UUIDField(help_text="ID del documento específico (pedido, cxp, etc.)")

    # Información del pago
    fecha_pago = models.DateTimeField()
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    id_moneda = models.ForeignKey("Moneda", on_delete=models.CASCADE, related_name="pagos")
    tasa = models.DecimalField(max_digits=18, decimal_places=4, default=1)

    # Método de pago
    id_metodo_pago = models.ForeignKey("MetodoPago", on_delete=models.CASCADE, related_name="pagos")

    # Referencias y observaciones
    referencia = models.CharField(max_length=100, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    # Asociación financiera (opcional - dependiendo del método)
    id_caja_fisica = models.ForeignKey(
        "CajaFisica",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos",
        help_text="Caja física donde se realizó el pago.",
    )
    id_caja_virtual = models.ForeignKey(
        "Caja",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_virtuales",
        help_text="Caja virtual que controla el ingreso/egreso financiero.",
    )
    id_cuenta_bancaria = models.ForeignKey(
        "CuentaBancariaEmpresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos",
        help_text="Cuenta bancaria origen/destino.",
    )
    id_datafono = models.ForeignKey(
        "Datafono",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos",
        help_text="Datafono utilizado para pagos con tarjeta.",
    )
    banco_destino = models.ForeignKey(
        "CuentaBancariaEmpresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_destino",
        help_text="Banco destino para métodos electrónicos/tarjeta.",
    )

    # Relación con transacción financiera (opcional - se crea automáticamente)
    id_transaccion_financiera = models.OneToOneField(
        "TransaccionFinanciera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pago_asociado",
        help_text="Transacción financiera generada automáticamente por este pago.",
    )

    # Relaciones opcionales a documentos específicos (para integridad referencial)
    id_pedido = models.ForeignKey(
        "ventas.Pedido", on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos_genericos"
    )
    id_nota_venta = models.ForeignKey(
        "ventas.NotaVenta", on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos_genericos"
    )
    id_factura = models.ForeignKey(
        "ventas.FacturaFiscal", on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos_genericos"
    )
    id_cxp = models.ForeignKey(
        "cuentas_por_pagar.CuentaPorPagar",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_genericos",
    )
    id_gasto = models.ForeignKey(
        "gastos.Gasto", on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos_genericos"
    )
    id_reembolso_gasto = models.ForeignKey(
        "gastos.ReembolsoGasto", on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos_genericos"
    )
    id_nomina = models.ForeignKey(
        "nomina.Nomina", on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos_genericos"
    )
    id_contribucion = models.ForeignKey(
        "fiscal.ContribucionParafiscal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_genericos",
    )

    # Auditoría
    id_usuario_registro = models.ForeignKey("core.Usuarios", on_delete=models.SET_NULL, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "finanzas_pago"
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        indexes = [
            models.Index(fields=["id_empresa", "tipo_operacion", "fecha_pago"]),
            models.Index(fields=["tipo_documento", "id_documento"]),
            models.Index(fields=["id_metodo_pago", "fecha_pago"]),
        ]

    def __str__(self):
        return f"{self.tipo_operacion} - {self.monto} ({self.get_tipo_documento_display()})"

    def save(self, *args, **kwargs):
        # Validaciones según tipo de documento
        self._validar_documento()
        super().save(*args, **kwargs)

    def _validar_documento(self):
        # R-CODE-1: cada rama valida que el documento pertenezca a la MISMA
        # empresa del pago — un id de otro tenant cuenta como inexistente.
        """Valida que el documento referenciado existe según el tipo"""
        if self.tipo_documento == "PEDIDO" and self.id_pedido:
            from apps.ventas.models import Pedido

            try:
                pedido = Pedido.objects.get(
                    id_pedido=self.id_pedido.id_pedido, id_empresa_id=self.id_empresa_id
                )
            except Pedido.DoesNotExist:
                raise ValueError(f"Pedido {self.id_pedido.id_pedido} no existe")

        elif self.tipo_documento == "NOTA_VENTA" and self.id_nota_venta:
            from apps.ventas.models import NotaVenta

            try:
                nota_venta = NotaVenta.objects.get(
                    id_nota_venta=self.id_nota_venta.id_nota_venta,
                    id_empresa_id=self.id_empresa_id,
                )
            except NotaVenta.DoesNotExist:
                raise ValueError(f"Nota de Venta {self.id_nota_venta.id_nota_venta} no existe")

        elif self.tipo_documento == "FACTURA" and self.id_factura:
            # FIX: FacturaFiscal vive en apps.ventas (el FK es "ventas.FacturaFiscal");
            # importarla desde apps.fiscal rompía con ImportError toda validación de factura.
            from apps.ventas.models import FacturaFiscal

            try:
                factura = FacturaFiscal.objects.get(
                    id_factura=self.id_factura.id_factura, id_empresa_id=self.id_empresa_id
                )
            except FacturaFiscal.DoesNotExist:
                raise ValueError(f"Factura Fiscal {self.id_factura.id_factura} no existe")

        elif self.tipo_documento == "CXP" and self.id_cxp:
            from apps.cuentas_por_pagar.models import CuentaPorPagar

            try:
                cxp = CuentaPorPagar.objects.get(
                    id_cxp=self.id_cxp.id_cxp, id_empresa_id=self.id_empresa_id
                )
            except CuentaPorPagar.DoesNotExist:
                raise ValueError(f"Cuenta por Pagar {self.id_cxp.id_cxp} no existe")

        elif self.tipo_documento == "GASTO" and self.id_gasto:
            from apps.gastos.models import Gasto

            try:
                gasto = Gasto.objects.get(
                    id_gasto=self.id_gasto.id_gasto, id_empresa_id=self.id_empresa_id
                )
            except Gasto.DoesNotExist:
                raise ValueError(f"Gasto {self.id_gasto.id_gasto} no existe")

        elif self.tipo_documento == "REEMBOLSO_GASTO" and self.id_reembolso_gasto:
            from apps.gastos.models import ReembolsoGasto

            # FIX: la PK del modelo es `id_reembolso` (no `id_reembolso_gasto`).
            try:
                reembolso = ReembolsoGasto.objects.get(
                    id_reembolso=self.id_reembolso_gasto.id_reembolso,
                    id_empresa_id=self.id_empresa_id,
                )
            except ReembolsoGasto.DoesNotExist:
                raise ValueError(f"Reembolso de Gasto {self.id_reembolso_gasto.id_reembolso} no existe")

        elif self.tipo_documento == "NOMINA" and self.id_nomina:
            from apps.nomina.models import Nomina

            try:
                nomina = Nomina.objects.get(
                    id_nomina=self.id_nomina.id_nomina,
                    # Nomina no tiene empresa directa: se acota vía su proceso.
                    id_proceso_nomina__id_empresa_id=self.id_empresa_id,
                )
            except Nomina.DoesNotExist:
                raise ValueError(f"Nómina {self.id_nomina.id_nomina} no existe")

        elif self.tipo_documento == "IMPUESTO" and self.id_contribucion:
            from apps.fiscal.models import ContribucionParafiscal

            # FIX: ContribucionParafiscal usa la PK implícita `pk`/`id`, no `id_contribucion`.
            try:
                contribucion = ContribucionParafiscal.objects.filter(
                    models.Q(empresa_id=self.id_empresa_id)
                    | models.Q(empresa__isnull=True)
                    | models.Q(es_publico=True)
                ).get(pk=self.id_contribucion.pk)
            except ContribucionParafiscal.DoesNotExist:
                raise ValueError(f"Contribución Parafiscal {self.id_contribucion.pk} no existe")

    @property
    def documento_relacionado(self):
        """Retorna el objeto del documento relacionado"""
        if self.tipo_documento == "PEDIDO" and self.id_pedido:
            return self.id_pedido
        elif self.tipo_documento == "NOTA_VENTA" and self.id_nota_venta:
            return self.id_nota_venta
        elif self.tipo_documento == "FACTURA" and self.id_factura:
            return self.id_factura
        elif self.tipo_documento == "CXP" and self.id_cxp:
            return self.id_cxp
        elif self.tipo_documento == "GASTO" and self.id_gasto:
            return self.id_gasto
        elif self.tipo_documento == "REEMBOLSO_GASTO" and self.id_reembolso_gasto:
            return self.id_reembolso_gasto
        elif self.tipo_documento == "NOMINA" and self.id_nomina:
            return self.id_nomina
        elif self.tipo_documento == "IMPUESTO" and self.id_contribucion:
            return self.id_contribucion
        return None


# ── Pagos de terceros (Zelle) — Capa B, tropicalización VE (§6.6 Plan Maestro) ─

from apps.core.base_models import IntegrationFieldsMixin, TenantModel  # noqa: E402


class PagoTercero(TenantModel, IntegrationFieldsMixin):
    """
    Cobro en divisas (típicamente USD vía Zelle) que entra por la cuenta de un
    PROVEEDOR (tercero), dinámica forzada por las restricciones para recibir
    USD en Venezuela (Plan Maestro §6.6, portado de GestionCxC
    ``routers/zelle_terceros.py``).

    Ciclo de vida (las transiciones las gobiernan los services de
    ``apps.finanzas.services_pagos_terceros`` — transición inválida → 400)::

        pendiente ──abonar──────────────→ abonado            (reduce CxP del proveedor)
        pendiente ──solicitar_reintegro─→ reintegro_pendiente (crea CxC contra el proveedor)
        reintegro_pendiente ──marcar_reintegrado─→ reintegrado
        pendiente ──anular──────────────→ anulado

    El proveedor es opcional al crear (un cobro puede originarse en caja sin
    saber aún por qué cuenta entró) y se fija con ``asociar_proveedor`` antes
    de abonar o solicitar reintegro.

    Puente proveedor→CxC (decisión de diseño): ``CuentaPorCobrar.cliente`` es
    opcional (ADR-009); el reintegro identifica al deudor con
    ``cliente_externo_id = "proveedor:<uuid>"`` + nombre denormalizado, sin
    crear un ``crm.Cliente`` espejo del proveedor.
    """

    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("abonado", "Abonado a CxP"),
        ("reintegro_pendiente", "Reintegro pendiente"),
        ("reintegrado", "Reintegrado"),
        ("anulado", "Anulado"),
    ]

    id_pago_tercero = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.CASCADE, related_name="pagos_terceros"
    )
    id_proveedor = models.ForeignKey(
        "proveedores.Proveedor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos_terceros",
        help_text="Proveedor por cuya cuenta entró el cobro. Opcional al crear "
                  "(cobro originado en caja); requerido para abonar o reintegrar.",
    )
    id_moneda = models.ForeignKey(
        "finanzas.Moneda", on_delete=models.PROTECT, related_name="pagos_terceros"
    )
    monto = models.DecimalField(
        max_digits=18, decimal_places=2, help_text="Monto del cobro recibido en la cuenta del tercero."
    )
    # La comisión NO genera asiento de gasto propio: queda anotada en el
    # documento_json y el asiento del reintegro va por el monto neto.
    comision = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Comisión que cobra el proveedor por el reintegro (opcional). "
                  "La CxC del reintegro se emite por monto − comisión.",
    )
    referencia_zelle = models.CharField(
        max_length=100, help_text="Referencia/confirmación de la transferencia Zelle."
    )
    fecha = models.DateField(help_text="Fecha del cobro en la cuenta del tercero.")
    concepto = models.TextField(blank=True, default="")
    estado = models.CharField(
        max_length=20, choices=ESTADO_CHOICES, default="pendiente", db_index=True
    )
    # Trazabilidad de los documentos generados por las acciones (SET_NULL: si el
    # documento destino se elimina, el pago conserva su historia en documento_json).
    id_abono_cxp = models.ForeignKey(
        "cuentas_por_pagar.AbonoCxP",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_terceros",
        help_text="Abono CxP generado por la acción 'abonar'.",
    )
    id_cxc_reintegro = models.ForeignKey(
        "cuentas_por_cobrar.CuentaPorCobrar",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reintegros_pago_tercero",
        help_text="CxC contra el proveedor generada por 'solicitar_reintegro'.",
    )

    class Meta:
        db_table = "finanzas_pago_tercero"
        verbose_name = "Pago de Tercero"
        verbose_name_plural = "Pagos de Terceros"
        ordering = ["-fecha", "-fecha_creacion"]
        indexes = [
            models.Index(fields=["id_empresa", "estado"]),
            models.Index(fields=["id_empresa", "id_proveedor"]),
        ]

    def __str__(self):
        proveedor = self.id_proveedor.razon_social if self.id_proveedor_id and self.id_proveedor else "sin proveedor"
        return f"PagoTercero {self.referencia_zelle} — {self.monto} ({proveedor}) [{self.estado}]"
