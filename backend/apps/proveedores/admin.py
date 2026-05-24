from django.contrib import admin

from .models import ContactoProveedor, CuentaBancariaProveedor, Proveedor

# Register your models here.
admin.site.register(Proveedor)

# Registraciones agregadas automáticamente


@admin.register(ContactoProveedor)
class ContactoProveedorAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]


@admin.register(CuentaBancariaProveedor)
class CuentaBancariaProveedorAdmin(admin.ModelAdmin):
    list_display = ["__str__"]
    search_fields = ["__str__"]
