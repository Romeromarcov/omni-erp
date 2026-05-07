from django.contrib import admin
from .models import (
    # Caja,
    MovimientoInternoFondo,
    OperacionCambioDivisa
)

# admin.site.register(Caja)
admin.site.register(MovimientoInternoFondo)

# Registraciones agregadas automáticamente

@admin.register(OperacionCambioDivisa)
class OperacionCambioDivisaAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
