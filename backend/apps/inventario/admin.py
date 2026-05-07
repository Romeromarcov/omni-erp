from django.contrib import admin
from .models import (
    UnidadMedida,
    CategoriaProducto,
    Producto,
    VarianteProducto,
    StockActual,
    MovimientoInventario,
    ConversionUnidadMedida,
    StockConsignacionCliente,
    StockConsignacionProveedor
)

# Register your models here.
admin.site.register(UnidadMedida)
admin.site.register(CategoriaProducto)
admin.site.register(Producto)

# Registraciones agregadas automáticamente

@admin.register(VarianteProducto)
class VarianteProductoAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(StockActual)
class StockActualAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(ConversionUnidadMedida)
class ConversionUnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(StockConsignacionCliente)
class StockConsignacionClienteAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(StockConsignacionProveedor)
class StockConsignacionProveedorAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
