from django.contrib import admin
from .models import (
    CategoriaTicket,
    TicketSoporte,
    InteraccionTicket,
    BaseConocimientoArticulo,
    FeedbackCliente
)
from . import models

@admin.register(CategoriaTicket)
class CategoriaTicketAdmin(admin.ModelAdmin):
    list_display = ['nombre_categoria']
    list_filter = ['activo']
    search_fields = ['nombre_categoria', 'descripcion']

@admin.register(TicketSoporte)
class TicketSoporteAdmin(admin.ModelAdmin):
    list_display = ['numero_ticket', 'asunto', 'estado_ticket', 'fecha_apertura', 'fecha_ultima_actualizacion']
    list_filter = ['prioridad', 'estado_ticket']
    search_fields = ['numero_ticket', 'asunto', 'descripcion']

@admin.register(InteraccionTicket)
class InteraccionTicketAdmin(admin.ModelAdmin):
    list_display = ['fecha_hora_interaccion', 'fecha_creacion']

@admin.register(BaseConocimientoArticulo)
class BaseConocimientoArticuloAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'fecha_publicacion', 'fecha_ultima_revision']
    list_filter = ['activo']
    search_fields = ['titulo']

@admin.register(FeedbackCliente)
class FeedbackClienteAdmin(admin.ModelAdmin):
    list_display = ['fecha_feedback']

