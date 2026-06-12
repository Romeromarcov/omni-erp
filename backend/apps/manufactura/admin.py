from django.contrib import admin

from .models import (
    CentroTrabajo,
    ConfiguracionManufactura,
    ConsumoMaterial,
    EtapaOrdenProduccion,
    EtapaProduccion,
    ListaMateriales,
    ListaMaterialesDetalle,
    OperacionProduccion,
    OrdenProduccion,
    ProduccionTerminada,
    RegistroOperacion,
    RutaProduccion,
    RutaProduccionDetalle,
)

admin.site.register(ListaMateriales)
admin.site.register(RutaProduccion)
admin.site.register(OrdenProduccion)
admin.site.register(ConsumoMaterial)
admin.site.register(ProduccionTerminada)

# Registraciones agregadas automáticamente


@admin.register(ListaMaterialesDetalle)
class ListaMaterialesDetalleAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(CentroTrabajo)
class CentroTrabajoAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(OperacionProduccion)
class OperacionProduccionAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(RutaProduccionDetalle)
class RutaProduccionDetalleAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(RegistroOperacion)
class RegistroOperacionAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(EtapaProduccion)
class EtapaProduccionAdmin(admin.ModelAdmin):
    list_display = ["empresa", "orden", "codigo", "nombre", "tarifa_destajo", "activo"]
    list_filter = ["empresa", "activo"]
    search_fields = ["codigo", "nombre"]


@admin.register(EtapaOrdenProduccion)
class EtapaOrdenProduccionAdmin(admin.ModelAdmin):
    list_display = ["orden_produccion", "orden", "etapa", "estado", "completada_por", "fecha_completada"]
    list_filter = ["estado"]


@admin.register(ConfiguracionManufactura)
class ConfiguracionManufacturaAdmin(admin.ModelAdmin):
    list_display = ["empresa", "porcentaje_overhead"]
