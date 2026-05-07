from django.contrib import admin
from .models import CuentaPorCobrar, AbonoCxC

@admin.register(CuentaPorCobrar)
class CuentaPorCobrarAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'monto', 'fecha_emision', 'fecha_vencimiento', 'estado')

@admin.register(AbonoCxC)
class AbonoCxCAdmin(admin.ModelAdmin):
    list_display = ('id', 'cuenta_por_cobrar', 'monto', 'fecha_abono', 'usuario')
