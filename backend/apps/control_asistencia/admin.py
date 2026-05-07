from django.contrib import admin
from .models import (
    HorarioTrabajo,
    AsignacionHorario,
    RegistroAsistencia,
    ResumenAsistenciaDiario
)
from . import models

@admin.register(HorarioTrabajo)
class HorarioTrabajoAdmin(admin.ModelAdmin):
    list_display = ['nombre_horario']
    list_filter = ['activo']
    search_fields = ['nombre_horario', 'descripcion']

@admin.register(AsignacionHorario)
class AsignacionHorarioAdmin(admin.ModelAdmin):
    list_display = ['fecha_inicio', 'fecha_fin']
    list_filter = ['activo']

@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(admin.ModelAdmin):
    list_display = ['fecha_hora_marcado', 'fecha_creacion']

@admin.register(ResumenAsistenciaDiario)
class ResumenAsistenciaDiarioAdmin(admin.ModelAdmin):
    list_display = ['estado_revision', 'fecha_creacion']

