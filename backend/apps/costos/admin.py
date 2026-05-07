from django.contrib import admin
from .models import (
    CostoProduccion,
    CostoEstandarProducto,
    AnalisisVariacionCosto
)

# Registraciones agregadas automáticamente

@admin.register(CostoProduccion)
class CostoProduccionAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(CostoEstandarProducto)
class CostoEstandarProductoAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(AnalisisVariacionCosto)
class AnalisisVariacionCostoAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
