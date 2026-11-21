from django.contrib import admin

from .models import Actividad, Cliente, ContactoCliente, DireccionCliente, Etapa, Lead, Pipeline

# Register your models here.
admin.site.register(Cliente)

# Registraciones agregadas automáticamente


@admin.register(ContactoCliente)
class ContactoClienteAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DireccionCliente)
class DireccionClienteAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ["nombre", "id_empresa", "es_predeterminado", "activo"]
    search_fields = ["nombre"]


@admin.register(Etapa)
class EtapaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "pipeline", "orden", "tipo", "activo"]
    search_fields = ["nombre"]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ["nombre", "apellido", "fuente", "pipeline", "etapa", "id_empresa"]
    search_fields = ["nombre", "apellido", "email", "telefono"]


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ["tipo", "asunto", "lead", "completada", "fecha_vencimiento", "id_empresa"]
    list_filter = ["tipo", "completada"]
    search_fields = ["asunto", "descripcion"]
