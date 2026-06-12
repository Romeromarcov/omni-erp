from django.contrib import admin

from .models import (
    ComisionVenta,
    Cotizacion,
    DetalleCotizacion,
    DetalleDevolucionVenta,
    DetalleFacturaFiscal,
    DetalleNotaCreditoFiscal,
    DetalleNotaCreditoVenta,
    DetalleNotaVenta,
    DetallePedido,
    DevolucionVenta,
    EsquemaComision,
    EsquemaComisionCategoria,
    FacturaFiscal,
    NotaCreditoFiscal,
    NotaCreditoVenta,
    NotaVenta,
    Pedido,
)

# Register your models here.
admin.site.register(Pedido)
admin.site.register(DetallePedido)
admin.site.register(NotaVenta)
admin.site.register(DetalleNotaVenta)
admin.site.register(FacturaFiscal)


@admin.register(EsquemaComision)
class EsquemaComisionAdmin(admin.ModelAdmin):
    list_display = ["vendedor", "porcentaje_base", "vigente_desde", "vigente_hasta", "activo"]
    list_filter = ["activo"]


@admin.register(EsquemaComisionCategoria)
class EsquemaComisionCategoriaAdmin(admin.ModelAdmin):
    list_display = ["esquema", "categoria", "porcentaje"]


@admin.register(ComisionVenta)
class ComisionVentaAdmin(admin.ModelAdmin):
    list_display = ["nota_venta", "vendedor", "monto", "estado", "fecha_devengo"]
    list_filter = ["estado"]

# Registraciones agregadas automáticamente


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DetalleCotizacion)
class DetalleCotizacionAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DetalleFacturaFiscal)
class DetalleFacturaFiscalAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(NotaCreditoVenta)
class NotaCreditoVentaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DetalleNotaCreditoVenta)
class DetalleNotaCreditoVentaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DevolucionVenta)
class DevolucionVentaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DetalleDevolucionVenta)
class DetalleDevolucionVentaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(NotaCreditoFiscal)
class NotaCreditoFiscalAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DetalleNotaCreditoFiscal)
class DetalleNotaCreditoFiscalAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]
