from django.contrib import admin

from .models import (
    CalendarioActivacion,
    EventoActivacion,
    RecursoActivacion,
    UsoRecursoEvento,
)

admin.site.register(CalendarioActivacion)
admin.site.register(RecursoActivacion)
admin.site.register(EventoActivacion)
admin.site.register(UsoRecursoEvento)
