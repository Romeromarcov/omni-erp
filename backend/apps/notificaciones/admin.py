from django.contrib import admin

from .models import (
    EventoNotificacion,
    LogNotificacion,
    PlantillaNotificacion,
    SuscripcionNotificacion,
)


@admin.register(PlantillaNotificacion)
class PlantillaNotificacionAdmin(admin.ModelAdmin):
    list_display = ["codigo_plantilla", "canal", "asunto", "activo"]
    list_filter = ["canal", "activo"]
    search_fields = ["codigo_plantilla", "asunto"]


@admin.register(EventoNotificacion)
class EventoNotificacionAdmin(admin.ModelAdmin):
    list_display = ["codigo_evento", "id_empresa", "activo"]
    list_filter = ["activo"]


@admin.register(SuscripcionNotificacion)
class SuscripcionNotificacionAdmin(admin.ModelAdmin):
    list_display = ["id_evento", "id_usuario", "canal", "activo"]
    list_filter = ["canal", "activo"]


@admin.register(LogNotificacion)
class LogNotificacionAdmin(admin.ModelAdmin):
    list_display = ["destinatario", "canal", "estado", "intentos", "fecha_creacion"]
    list_filter = ["canal", "estado"]
