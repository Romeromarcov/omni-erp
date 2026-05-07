from django.contrib import admin
from .models import (
    Cliente,
    ContactoCliente,
    DireccionCliente
)

# Register your models here.
admin.site.register(Cliente)

# Registraciones agregadas automáticamente

@admin.register(ContactoCliente)
class ContactoClienteAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']

@admin.register(DireccionCliente)
class DireccionClienteAdmin(admin.ModelAdmin):
    list_display = ['__str__']
    search_fields = ['__str__']
