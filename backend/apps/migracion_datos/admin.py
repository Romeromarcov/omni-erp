from django.contrib import admin

from .models import DetalleErrorMigracion, PlantillaMigracion, ProcesoMigracion

admin.site.register(PlantillaMigracion)
admin.site.register(ProcesoMigracion)
admin.site.register(DetalleErrorMigracion)
