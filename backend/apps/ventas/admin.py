from django.contrib import admin
from .models import (
    Pedido,
    DetallePedido,
    NotaVenta,
    DetalleNotaVenta,
    FacturaFiscal,
    Cotizacion,
    DetalleCotizacion,
    DetalleFacturaFiscal,
    NotaCreditoVenta,
    DetalleNotaCreditoVenta,
    DevolucionVenta,
    DetalleDevolucionVenta,
    NotaCreditoFiscal,
    DetalleNotaCreditoFiscal
)

# Register your models here.
admin.site.register(Pedido)
admin.site.register(DetallePedido)
admin.site.register(NotaVenta)
admin.site.register(DetalleNotaVenta)
admin.site.register(FacturaFiscal)

# Registraciones agregadas automáticamente

@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleCotizacion)
class DetalleCotizacionAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleFacturaFiscal)
class DetalleFacturaFiscalAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(NotaCreditoVenta)
class NotaCreditoVentaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleNotaCreditoVenta)
class DetalleNotaCreditoVentaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DevolucionVenta)
class DevolucionVentaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleDevolucionVenta)
class DetalleDevolucionVentaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(NotaCreditoFiscal)
class NotaCreditoFiscalAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleNotaCreditoFiscal)
class DetalleNotaCreditoFiscalAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
