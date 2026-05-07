from rest_framework import serializers
from .models import Proveedor, ContactoProveedor, CuentaBancariaProveedor

class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = '__all__'


class ContactoProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactoProveedor
        fields = '__all__'


class CuentaBancariaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaBancariaProveedor
        fields = '__all__'
