from django.contrib import admin

from .models import (
    AreaOperativa,
    ComentarioTarea,
    ConfiguracionSeguimientoTareas,
    DependenciaTarea,
    MiembroAreaOperativa,
    MinutaReunion,
    PlantillaTareaRecurrente,
    Proyecto,
    RegistroAlertaTarea,
    SeccionProyecto,
    Tarea,
)

admin.site.register(AreaOperativa)
admin.site.register(MiembroAreaOperativa)
admin.site.register(Proyecto)
admin.site.register(SeccionProyecto)
admin.site.register(PlantillaTareaRecurrente)
admin.site.register(MinutaReunion)
admin.site.register(Tarea)
admin.site.register(DependenciaTarea)
admin.site.register(ComentarioTarea)
admin.site.register(ConfiguracionSeguimientoTareas)
admin.site.register(RegistroAlertaTarea)
