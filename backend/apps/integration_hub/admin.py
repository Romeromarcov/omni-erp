from django.contrib import admin

from .models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)


@admin.register(ConectorProveedor)
class ConectorProveedorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "codigo", "estado", "activo", "orden"]
    list_filter = ["estado", "activo"]
    search_fields = ["nombre", "codigo"]
    ordering = ["orden", "nombre"]


@admin.register(ConectorInstancia)
class ConectorInstanciaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "id_empresa", "id_proveedor", "estado", "ultimo_sync", "activo"]
    list_filter = ["estado", "activo", "id_proveedor"]
    search_fields = ["nombre"]
    readonly_fields = ["fecha_creacion", "fecha_actualizacion", "ultimo_test_conexion", "ultimo_sync"]
    # NUNCA mostrar configuracion en admin (R-CODE-8)
    exclude = ["configuracion"]


@admin.register(JobSincronizacion)
class JobSincronizacionAdmin(admin.ModelAdmin):
    list_display = ["id_job", "id_instancia", "tipo_entidad", "estado",
                    "total_registros", "creados", "fallidos", "iniciado_en"]
    list_filter = ["estado", "tipo_entidad", "direccion"]
    search_fields = ["id_instancia__nombre"]
    readonly_fields = ["iniciado_en", "completado_en", "celery_task_id"]


@admin.register(EntidadSincronizada)
class EntidadSincronizadaAdmin(admin.ModelAdmin):
    list_display = ["tipo_entidad", "id_externo", "id_omni", "id_instancia", "ultimo_sync"]
    list_filter = ["tipo_entidad", "activo"]
    search_fields = ["id_externo", "id_omni"]


@admin.register(LogDetalleSincronizacion)
class LogDetalleSincronizacionAdmin(admin.ModelAdmin):
    list_display = ["operacion", "id_externo", "id_omni", "id_job", "creado_en"]
    list_filter = ["operacion"]
    readonly_fields = ["creado_en"]
