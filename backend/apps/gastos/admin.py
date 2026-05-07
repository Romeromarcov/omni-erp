from django.contrib import admin
from .models import (
    CategoriaGasto,
    Gasto,
    ReembolsoGasto
)
from . import models

@admin.register(CategoriaGasto)
class CategoriaGastoAdmin(admin.ModelAdmin):
    list_display = ['nombre_categoria']
    list_filter = ['activo']
    search_fields = ['nombre_categoria', 'descripcion']

@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ['fecha_gasto', 'estado_gasto', 'fecha_creacion']
    list_filter = ['estado_gasto']
    search_fields = ['descripcion']

@admin.register(ReembolsoGasto)
class ReembolsoGastoAdmin(admin.ModelAdmin):
    list_display = ['fecha_reembolso', 'estado_reembolso', 'fecha_creacion']

