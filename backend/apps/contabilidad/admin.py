from django.contrib import admin

from .models import AsientoContable, DetalleAsiento, DiarioContable, MapeoContable, PeriodoContable, PlanCuentas


@admin.register(PlanCuentas)
class PlanCuentasAdmin(admin.ModelAdmin):
    list_display = ["codigo_cuenta", "nombre_cuenta", "fecha_creacion"]
    list_filter = ["activo"]
    search_fields = ["nombre_cuenta"]


@admin.register(DiarioContable)
class DiarioContableAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "tipo", "prefijo_secuencia", "siguiente_numero", "activo"]
    list_filter = ["tipo", "activo"]
    search_fields = ["codigo", "nombre"]


@admin.register(PeriodoContable)
class PeriodoContableAdmin(admin.ModelAdmin):
    list_display = ["id_empresa", "anio", "mes", "estado", "fecha_cierre", "activo"]
    list_filter = ["estado", "anio", "activo"]
    search_fields = ["observaciones"]


@admin.register(AsientoContable)
class AsientoContableAdmin(admin.ModelAdmin):
    list_display = [
        "fecha_asiento",
        "numero_asiento",
        "id_diario",
        "nombre_modelo_origen",
        "estado_asiento",
        "es_cierre",
        "fecha_creacion",
    ]
    list_filter = ["estado_asiento", "es_cierre"]
    search_fields = ["numero_asiento", "descripcion", "nombre_modelo_origen"]


@admin.register(DetalleAsiento)
class DetalleAsientoAdmin(admin.ModelAdmin):
    list_display = ["id_asiento", "id_cuenta_contable", "id_contacto", "debe", "haber", "fecha_creacion"]
    search_fields = ["descripcion_detalle"]


@admin.register(MapeoContable)
class MapeoContableAdmin(admin.ModelAdmin):
    list_display = ["id_empresa", "tipo_asiento", "id_diario", "activo", "fecha_creacion"]
    list_filter = ["tipo_asiento", "activo"]
