from django.contrib import admin

from .models import LogAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = (
        "fecha_hora_accion",
        "id_empresa",
        "id_usuario",
        "modulo",
        "tipo_accion",
        "nombre_entidad_afectada",
        "id_entidad_afectada",
    )
    list_filter = ("modulo", "tipo_accion", "nombre_entidad_afectada")
    search_fields = ("tipo_accion", "nombre_entidad_afectada", "id_entidad_afectada", "descripcion_accion")
    readonly_fields = (
        "id_log_auditoria",
        "id_empresa",
        "id_usuario",
        "id_entidad_afectada",
        "nombre_entidad_afectada",
        "modulo",
        "tipo_accion",
        "descripcion_accion",
        "cambios_json",
        "fecha_hora_accion",
        "direccion_ip",
        "navegador_info",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
