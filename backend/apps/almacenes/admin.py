from django.contrib import admin

from .models import Almacen, UbicacionAlmacen

# Register your models here.
admin.site.register(Almacen)

# Registraciones agregadas automáticamente


@admin.register(UbicacionAlmacen)
class UbicacionAlmacenAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]
