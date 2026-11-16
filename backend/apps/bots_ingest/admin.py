from django.contrib import admin

from .models import BotBitacora, BotLatidoDiario, BotRegistro, BotUsuario, IngestaBot

admin.site.register(BotUsuario)
admin.site.register(IngestaBot)
admin.site.register(BotRegistro)
admin.site.register(BotLatidoDiario)
@admin.register(BotBitacora)
class BotBitacoraAdmin(admin.ModelAdmin):
    list_display = ("id_empresa", "entidad", "accion", "actor", "fecha_creacion")
    readonly_fields = ("id_empresa", "entidad", "accion", "antes", "despues", "actor", "fecha_creacion")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
