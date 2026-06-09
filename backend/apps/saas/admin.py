"""
Registro en Django admin del módulo SaaS (Plan C — Fase C2).

Sirve como respaldo operativo del proveedor: gestionar planes y suscripciones
desde el admin cuando la consola `/admin-saas` no esté disponible. El acceso al
admin ya está restringido a `is_staff`; aquí no se relaja ningún permiso.
"""
from django.contrib import admin

from .models import Plan, Suscripcion


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "nombre", "nivel", "precio_mensual", "precio_anual",
        "max_usuarios", "max_empresas", "permite_ia", "permite_api", "activo",
    )
    list_filter = ("nivel", "activo", "permite_ia", "permite_api", "soporte")
    search_fields = ("nombre", "nivel")
    ordering = ("precio_mensual",)


@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display = (
        "id_suscripcion", "id_empresa", "id_plan", "estado", "periodo",
        "fecha_inicio", "fecha_fin", "renovacion_automatica",
    )
    list_filter = ("estado", "periodo", "renovacion_automatica")
    search_fields = ("id_empresa__nombre_legal", "id_empresa__nombre_comercial", "referencia_pago")
    list_select_related = ("id_empresa", "id_plan")
    autocomplete_fields = ("id_empresa", "id_plan")
    date_hierarchy = "fecha_inicio"
    readonly_fields = ("fecha_cancelacion", "fecha_suspension", "fecha_creacion", "fecha_actualizacion")
