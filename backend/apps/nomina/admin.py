from django.contrib import admin

from .models import (
    ConceptoNomina,
    DetalleNomina,
    Nomina,
    NominaExtrasalarial,
    PeriodoNomina,
    ProcesoNomina,
    ProcesoNominaExtrasalarial,
)

# Register your models here.

# Registraciones agregadas automáticamente


@admin.register(PeriodoNomina)
class PeriodoNominaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(ConceptoNomina)
class ConceptoNominaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(ProcesoNomina)
class ProcesoNominaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(Nomina)
class NominaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(DetalleNomina)
class DetalleNominaAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(ProcesoNominaExtrasalarial)
class ProcesoNominaExtrasalarialAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(NominaExtrasalarial)
class NominaExtrasalarialAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]
