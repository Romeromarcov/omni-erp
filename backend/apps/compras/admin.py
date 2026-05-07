from django.contrib import admin
from .models import (
    OrdenCompra,
    DetalleOrdenCompra,
    RecepcionMercancia,
    FacturaCompra,
    RequisicionCompra,
    DetalleRequisicionCompra,
    SolicitudCotizacion,
    DetalleSolicitudCotizacion,
    OfertaProveedor,
    DetalleOfertaProveedor,
    DetalleRecepcionMercancia,
    DetalleFacturaCompra
)

# Register your models here.
admin.site.register(OrdenCompra)
admin.site.register(DetalleOrdenCompra)
admin.site.register(RecepcionMercancia)
admin.site.register(FacturaCompra)

# Registraciones agregadas automáticamente

@admin.register(RequisicionCompra)
class RequisicionCompraAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleRequisicionCompra)
class DetalleRequisicionCompraAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(SolicitudCotizacion)
class SolicitudCotizacionAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleSolicitudCotizacion)
class DetalleSolicitudCotizacionAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(OfertaProveedor)
class OfertaProveedorAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleOfertaProveedor)
class DetalleOfertaProveedorAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleRecepcionMercancia)
class DetalleRecepcionMercanciaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DetalleFacturaCompra)
class DetalleFacturaCompraAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
