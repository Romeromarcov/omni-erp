from django.contrib import admin
from .models import PlantillaMigracion, ProcesoMigracion, DetalleErrorMigracion

admin.site.register(PlantillaMigracion)
admin.site.register(ProcesoMigracion)
admin.site.register(DetalleErrorMigracion)
