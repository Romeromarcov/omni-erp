from django.contrib import admin
from .abonos import AbonoCxC

@admin.register(AbonoCxC)
class AbonoCxCAdmin(admin.ModelAdmin):
    list_display = ('id', 'cuenta_por_cobrar', 'monto', 'fecha_abono', 'usuario')
