from rest_framework import serializers

from .models import ContactoProveedor, CuentaBancariaProveedor, Proveedor


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_proveedor",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "referencia_externa",
            "documento_json",
            "razon_social",
            "nombre_comercial",
            "rif",
            "direccion",
            "telefono",
            "email",
            "id_empresa",
            "contacto",
        ]


class ContactoProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactoProveedor
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_contacto",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "nombre",
            "apellido",
            "cargo",
            "telefono",
            "email",
            "es_contacto_principal",
            "area_responsabilidad",
            "observaciones",
            "id_proveedor",
        ]


class CuentaBancariaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaBancariaProveedor
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_cuenta_bancaria",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "nombre_banco",
            "numero_cuenta",
            "tipo_cuenta",
            "titular_cuenta",
            "identificacion_titular",
            "es_cuenta_principal",
            "observaciones",
            "id_proveedor",
            "moneda",
        ]
