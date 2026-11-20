from django.contrib import admin

from .models import Almacen, StockUbicacion, UbicacionAlmacen

# Register your models here.
admin.site.register(Almacen)

# Registraciones agregadas automáticamente


@admin.register(UbicacionAlmacen)
class UbicacionAlmacenAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(StockUbicacion)
class StockUbicacionAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]
