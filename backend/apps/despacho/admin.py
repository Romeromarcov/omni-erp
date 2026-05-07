from django.contrib import admin
from .models import (
    Despacho,
    DetalleDespacho
)

# Registraciones agregadas automáticamente

@admin.register(Despacho)
class DespachoAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleDespacho)
class DetalleDespachoAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
