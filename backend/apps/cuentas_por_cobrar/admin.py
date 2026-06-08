from django.contrib import admin

from .models import AbonoCxC, CuentaPorCobrar


@admin.register(CuentaPorCobrar)
class CuentaPorCobrarAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente_display", "monto", "fecha_emision", "fecha_vencimiento", "estado")
    list_select_related = ("cliente",)

    @admin.display(description="Cliente")
    def cliente_display(self, obj):
        return obj.cliente_display


@admin.register(AbonoCxC)
class AbonoCxCAdmin(admin.ModelAdmin):
    list_display = ("id", "cuenta_por_cobrar", "monto", "fecha_abono", "usuario")
