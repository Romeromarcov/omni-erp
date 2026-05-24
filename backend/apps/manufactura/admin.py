from django.contrib import admin

from .models import (
    CentroTrabajo,
    ConsumoMaterial,
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
