from django.contrib import admin
from .models import (
    Empleado,
    Cargo,
    Beneficio,
    BeneficioEmpleado,
    TipoLicencia,
    LicenciaEmpleado
)

admin.site.register(Empleado)
admin.site.register(Cargo)

# Registraciones agregadas automáticamente

@admin.register(Beneficio)
class BeneficioAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(BeneficioEmpleado)
class BeneficioEmpleadoAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(TipoLicencia)
class TipoLicenciaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(LicenciaEmpleado)
class LicenciaEmpleadoAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
