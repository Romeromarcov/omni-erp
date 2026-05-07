from django.contrib import admin
from django import forms
from django.utils import timezone
from .models import Moneda, TasaCambio, MetodoPago, TransaccionFinanciera, Caja, CajaFisica, CuentaBancariaEmpresa, MovimientoCajaBanco, MonedaEmpresaActiva, MetodoPagoEmpresaActiva, SesionCajaFisica, Datafono, TransaccionDatafono, CajaUsuario, PlantillaMaestroCajasVirtuales, CajaVirtualAuto, CajaMetodoPagoOverride, SesionDatafono, DepositoDatafono, Pago, CajaFisicaUsuario

@admin.register(Datafono)
class DatafonoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'serial', 'id_empresa', 'id_sucursal', 'id_caja_fisica', 'id_cuenta_bancaria_asociada', 'comision_porcentaje', 'activo')
    search_fields = ('nombre', 'serial')
    list_filter = ('activo', 'id_empresa', 'id_sucursal')

@admin.register(TransaccionDatafono)
class TransaccionDatafonoAdmin(admin.ModelAdmin):
    list_display = ('id_datafono', 'monto', 'referencia_bancaria', 'fecha_hora_transaccion', 'conciliada', 'id_usuario_registro')
    search_fields = ('referencia_bancaria',)
    list_filter = ('conciliada', 'id_datafono')

@admin.register(SesionCajaFisica)
class SesionCajaFisicaAdmin(admin.ModelAdmin):
    list_display = ("id_sesion", "usuario", "caja_fisica", "fecha_apertura", "fecha_cierre", "estado")
    search_fields = ("usuario__username", "caja_fisica__nombre")
    list_filter = ("estado", "caja_fisica")
    readonly_fields = ('id_sesion', 'fecha_apertura')

@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    list_display = ('codigo_iso', 'nombre', 'simbolo', 'decimales', 'activo', 'fecha_creacion')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('codigo_iso', 'nombre')
    readonly_fields = ('id_moneda', 'fecha_creacion')


@admin.register(TasaCambio)
class TasaCambioAdmin(admin.ModelAdmin):
    list_display = ('id_moneda_origen', 'id_moneda_destino', 'tipo_tasa', 'valor_tasa', 'fecha_tasa', 'id_empresa')
    list_filter = ('tipo_tasa', 'fecha_tasa', 'id_empresa')
    search_fields = ('id_moneda_origen__codigo_iso', 'id_moneda_destino__codigo_iso')
    readonly_fields = ('id_tasa_cambio', 'fecha_creacion')



@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ('nombre_metodo', 'tipo_metodo', 'empresa', 'activo', 'fecha_creacion')
    list_filter = ('tipo_metodo', 'activo', 'empresa')
    search_fields = ('nombre_metodo',)
    readonly_fields = ('id_metodo_pago', 'fecha_creacion')



@admin.register(TransaccionFinanciera)
class TransaccionFinancieraAdmin(admin.ModelAdmin):
    list_display = ['id_transaccion', 'tipo_transaccion', 'monto_transaccion', 'id_empresa', 'id_moneda_transaccion', 'id_metodo_pago', 'fecha_hora_transaccion', 'referencia_pago', 'descripcion', 'id_usuario_registro', 'fecha_creacion']
    search_fields = ['id_transaccion', 'referencia_pago', 'descripcion']


@admin.register(Caja)
class CajaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo_caja', 'sucursal', 'activa', 'fecha_creacion']
    search_fields = ['nombre']
    list_filter = ['activa', 'tipo_caja', 'sucursal', 'empresa']
    filter_horizontal = ['metodos_pago']
    readonly_fields = ('id_caja', 'fecha_creacion')

@admin.register(CajaFisica)
class CajaFisicaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo_caja', 'nombre_dispositivo', 'tipo_dispositivo', 'sucursal', 'activa', 'requiere_sesion_activa', 'cajas_virtuales_list', 'datafonos_list']
    search_fields = ['nombre', 'nombre_dispositivo', 'identificador_dispositivo']
    list_filter = ['activa', 'tipo_caja', 'tipo_dispositivo', 'sucursal', 'empresa']
    readonly_fields = ('id_caja_fisica', 'fecha_creacion')

    def cajas_virtuales_list(self, obj):
        cajas = obj.cajas_virtuales.all()
        if cajas:
            return ", ".join([f"{c.nombre} ({c.moneda.codigo_iso})" for c in cajas])
        return "Ninguna"
    cajas_virtuales_list.short_description = 'Cajas Virtuales'

    def datafonos_list(self, obj):
        datafonos = obj.datafonos.all()
        if datafonos:
            return ", ".join([f"{d.nombre} ({d.serial})" for d in datafonos])
        return "Ninguno"
    datafonos_list.short_description = 'Datafonos'

@admin.register(CuentaBancariaEmpresa)
class CuentaBancariaEmpresaAdmin(admin.ModelAdmin):
    list_display = ['nombre_banco', 'numero_cuenta', 'tipo_cuenta', 'saldo_actual', 'activo']
    search_fields = ['nombre_banco', 'numero_cuenta']

@admin.register(MovimientoCajaBanco)
class MovimientoCajaBancoAdmin(admin.ModelAdmin):
    list_display = ['tipo_movimiento', 'monto', 'fecha_movimiento', 'id_moneda', 'id_caja', 'id_cuenta_bancaria', 'id_empresa', 'id_usuario_registro']
    search_fields = ['concepto', 'referencia']

    actions = ['crear_ajuste']

    def crear_ajuste(self, request, queryset):
        from django import forms
        from apps.core.models import Empresa, Usuarios
        from apps.finanzas.models import Moneda, Caja, CuentaBancariaEmpresa
        from apps.finanzas.ajustes import crear_ajuste_caja_banco
        class AjusteCajaBancoForm(forms.Form):
            empresa = forms.ModelChoiceField(queryset=Empresa.objects.all())
            monto = forms.DecimalField(max_digits=18, decimal_places=2)
            moneda = forms.ModelChoiceField(queryset=Moneda.objects.all())
            caja = forms.ModelChoiceField(queryset=Caja.objects.all(), required=False)
            cuenta_bancaria = forms.ModelChoiceField(queryset=CuentaBancariaEmpresa.objects.all(), required=False)
            usuario = forms.ModelChoiceField(queryset=Usuarios.objects.all())
            motivo = forms.CharField(max_length=255, required=False)
            tipo_ajuste = forms.ChoiceField(choices=[('POSITIVO', 'Ajuste Positivo'), ('NEGATIVO', 'Ajuste Negativo')])
            referencia = forms.CharField(max_length=100, required=False)

        if 'apply' in request.POST:
            form = AjusteCajaBancoForm(request.POST)
            if form.is_valid():
                crear_ajuste_caja_banco(
                    empresa=form.cleaned_data['empresa'],
                    monto=form.cleaned_data['monto'],
                    moneda=form.cleaned_data['moneda'],
                    caja=form.cleaned_data['caja'],
                    cuenta_bancaria=form.cleaned_data['cuenta_bancaria'],
                    usuario=form.cleaned_data['usuario'],
                    motivo=form.cleaned_data['motivo'],
                    tipo_ajuste=form.cleaned_data['tipo_ajuste'],
                    referencia=form.cleaned_data['referencia'],
                )
                self.message_user(request, "Ajuste creado correctamente.")
                return None
        else:
            form = AjusteCajaBancoForm()
        from django.shortcuts import render
        return render(request, 'admin/ajuste_caja_banco.html', {'form': form})
    crear_ajuste.short_description = "Crear ajuste de caja/banco"

@admin.register(MonedaEmpresaActiva)
class MonedaEmpresaActivaAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'moneda', 'activa')
    list_filter = ('empresa', 'activa')
    search_fields = ('empresa__nombre', 'moneda__nombre', 'moneda__codigo_iso')
    readonly_fields = ('id',)

@admin.register(MetodoPagoEmpresaActiva)
class MetodoPagoEmpresaActivaAdmin(admin.ModelAdmin):
    def metodo_pago_nombre(self, obj):
        return getattr(obj.metodo_pago, 'nombre_metodo', str(obj.metodo_pago))

    def monedas_asociadas(self, obj):
        return ", ".join([m.nombre for m in obj.metodo_pago.monedas.all()])

    list_display = ('empresa', 'metodo_pago_nombre', 'activa', 'monedas_asociadas')
    list_filter = ('empresa', 'activa')
    search_fields = ('empresa__nombre', 'metodo_pago__nombre_metodo', 'monedas__nombre')
    readonly_fields = ('id', 'monedas_asociadas')


@admin.register(CajaUsuario)
class CajaUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'caja', 'es_predeterminada', 'fecha_asignacion')
    list_filter = ('es_predeterminada', 'caja__empresa')
    search_fields = ('usuario__username', 'usuario__first_name', 'usuario__last_name', 'caja__nombre')
    readonly_fields = ('id', 'fecha_asignacion')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('usuario', 'caja')

@admin.register(PlantillaMaestroCajasVirtuales)
class PlantillaMaestroCajasVirtualesAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'empresa', 'aplicar_a_todas_cajas_fisicas', 'aplicar_a_empleados_con_rol', 'activa', 'creada_por']
    search_fields = ['nombre', 'descripcion']
    list_filter = ['activa', 'aplicar_a_todas_cajas_fisicas', 'empresa']
    filter_horizontal = ['metodos_pago_base']
    readonly_fields = ('id_plantilla_maestro', 'fecha_creacion', 'fecha_modificacion')

    actions = ['sincronizar_cajas']

    def sincronizar_cajas(self, request, queryset):
        for plantilla in queryset:
            plantilla.sincronizar_cajas_virtuales()
        self.message_user(request, f"Sincronización completada para {queryset.count()} plantillas.")
    sincronizar_cajas.short_description = "Sincronizar cajas virtuales"


@admin.register(CajaVirtualAuto)
class CajaVirtualAutoAdmin(admin.ModelAdmin):
    list_display = ['plantilla_maestro', 'caja_fisica', 'empleado', 'moneda', 'metodo_pago', 'activa']
    search_fields = ['plantilla_maestro__nombre', 'caja_fisica__nombre', 'empleado__username']
    list_filter = ['activa', 'creada_automaticamente', 'plantilla_maestro', 'moneda', 'metodo_pago']
    readonly_fields = ('id_caja_virtual', 'fecha_creacion', 'fecha_modificacion')


@admin.register(CajaMetodoPagoOverride)
class CajaMetodoPagoOverrideAdmin(admin.ModelAdmin):
    list_display = ['caja_fisica', 'metodo_pago', 'sucursal', 'deshabilitado', 'creado_por', 'fecha_creacion']
    search_fields = ['caja_fisica__nombre', 'metodo_pago__nombre_metodo', 'motivo']
    list_filter = ['deshabilitado', 'sucursal', 'creado_por']
    readonly_fields = ('id_override', 'fecha_creacion')


@admin.register(SesionDatafono)
class SesionDatafonoAdmin(admin.ModelAdmin):
    list_display = ['datafono', 'usuario_apertura', 'fecha_apertura', 'estado', 'total_transacciones', 'neto_esperado']
    list_filter = ['estado', 'datafono', 'fecha_apertura']
    search_fields = ['datafono__nombre', 'datafono__serial', 'usuario_apertura__username']
    readonly_fields = ('id_sesion', 'fecha_apertura', 'fecha_modificacion')

    def neto_esperado(self, obj):
        return obj.neto_esperado
    neto_esperado.short_description = 'Neto Esperado'


@admin.register(DepositoDatafono)
class DepositoDatafonoAdmin(admin.ModelAdmin):
    list_display = ['lote_bancario', 'datafono', 'fecha_envio', 'estado', 'total_bruto', 'total_neto', 'usuario_envio']
    list_filter = ['estado', 'datafono', 'fecha_envio']
    search_fields = ['lote_bancario', 'referencia_banco', 'datafono__nombre']
    readonly_fields = ('id_deposito', 'fecha_creacion', 'fecha_modificacion')

    actions = ['marcar_como_recibido', 'conciliar_deposito']

    def marcar_como_recibido(self, request, queryset):
        queryset.update(estado='RECIBIDO', fecha_recepcion_banco=timezone.now())
        self.message_user(request, f"{queryset.count()} depósitos marcados como recibidos.")
    marcar_como_recibido.short_description = "Marcar como recibido en banco"

    def conciliar_deposito(self, request, queryset):
        # Esta acción requeriría más lógica para seleccionar el movimiento bancario correspondiente
        self.message_user(request, "Use la función conciliar() en el modelo para conciliaciones individuales.")
    conciliar_deposito.short_description = "Conciliar depósito (requiere movimiento bancario)"


@admin.register(CajaFisicaUsuario)
class CajaFisicaUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'caja_fisica', 'es_predeterminada', 'puede_abrir_sesion', 'puede_cerrar_sesion', 'fecha_asignacion')
    list_filter = ('es_predeterminada', 'puede_abrir_sesion', 'puede_cerrar_sesion', 'caja_fisica__empresa', 'caja_fisica__sucursal')
    search_fields = ('usuario__username', 'usuario__email', 'caja_fisica__nombre')
    readonly_fields = ('id', 'fecha_asignacion')

    fieldsets = (
        ('Asignación', {
            'fields': ('usuario', 'caja_fisica')
        }),
        ('Configuración', {
            'fields': ('es_predeterminada', 'puede_abrir_sesion', 'puede_cerrar_sesion')
        }),
        ('Información', {
            'fields': ('fecha_asignacion',),
            'classes': ('collapse',)
        })
    )


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id_pago', 'tipo_operacion', 'tipo_documento', 'monto', 'id_moneda', 'id_metodo_pago', 'fecha_pago', 'id_empresa')
    list_filter = ('tipo_operacion', 'tipo_documento', 'id_metodo_pago', 'fecha_pago', 'id_empresa')
    search_fields = ('id_pago', 'referencia', 'id_documento')
    readonly_fields = ('id_pago', 'fecha_creacion', 'fecha_actualizacion')

    fieldsets = (
        ('Información Básica', {
            'fields': ('id_pago', 'id_empresa', 'tipo_operacion', 'tipo_documento', 'id_documento')
        }),
        ('Detalles del Pago', {
            'fields': ('fecha_pago', 'monto', 'id_moneda', 'tasa', 'id_metodo_pago')
        }),
        ('Referencias Financieras', {
            'fields': ('id_caja_fisica', 'id_caja_virtual', 'id_cuenta_bancaria', 'id_datafono', 'banco_destino'),
            'classes': ('collapse',)
        }),
        ('Referencias Documentales', {
            'fields': ('id_pedido', 'id_nota_venta', 'id_factura', 'id_cxp', 'id_gasto', 'id_reembolso_gasto', 'id_nomina', 'id_contribucion'),
            'classes': ('collapse',)
        }),
        ('Información Adicional', {
            'fields': ('referencia', 'observaciones', 'id_transaccion_financiera', 'id_usuario_registro'),
            'classes': ('collapse',)
        }),
        ('Auditoría', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        })
    )
