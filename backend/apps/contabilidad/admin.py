from django.contrib import admin
from .models import (
    PlanCuentas,
    AsientoContable,
    DetalleAsiento
)
from . import models

@admin.register(PlanCuentas)
class PlanCuentasAdmin(admin.ModelAdmin):
    list_display = ['codigo_cuenta', 'nombre_cuenta', 'fecha_creacion']
    list_filter = ['activo']
    search_fields = ['nombre_cuenta']

@admin.register(AsientoContable)
class AsientoContableAdmin(admin.ModelAdmin):
    list_display = ['fecha_asiento', 'numero_asiento', 'nombre_modelo_origen', 'estado_asiento', 'fecha_creacion']
    list_filter = ['estado_asiento']
    search_fields = ['numero_asiento', 'descripcion', 'nombre_modelo_origen']

@admin.register(DetalleAsiento)
class DetalleAsientoAdmin(admin.ModelAdmin):
    list_display = ['fecha_creacion']
    search_fields = ['descripcion_detalle']

