from django.contrib import admin

from .models import Perfil, Tarjeta, Toque


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("slug", "nombre_publico", "id_empresa", "activo")
    search_fields = ("slug", "nombre_publico")


@admin.register(Tarjeta)
class TarjetaAdmin(admin.ModelAdmin):
    list_display = ("uid_chip", "tipo", "estado", "perfil", "id_empresa")
    list_filter = ("tipo", "estado")
    search_fields = ("uid_chip",)


@admin.register(Toque)
class ToqueAdmin(admin.ModelAdmin):
    list_display = ("fecha_toque", "perfil", "origen", "dispositivo", "id_empresa")
    list_filter = ("origen", "dispositivo")
