from rest_framework import serializers

from .models import Cliente, ContactoCliente, DireccionCliente


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_cliente",
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
            "tipo_cliente",
            "limite_credito",
            "dias_credito",
            "id_empresa",
            "contacto",
        ]


class ContactoClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactoCliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_contacto",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "nombre_contacto",
            "apellido_contacto",
            "cargo",
            "telefono_directo",
            "telefono_movil",
            "email_contacto",
            "fecha_nacimiento",
            "es_contacto_principal",
            "observaciones",
            "id_empresa",
            "id_cliente",
        ]


class DireccionClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DireccionCliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_direccion",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "tipo_direccion",
            "direccion_completa",
            "ciudad",
            "estado_provincia",
            "codigo_postal",
            "pais",
            "telefono",
            "persona_contacto",
            "es_direccion_principal",
            "observaciones",
            "id_empresa",
            "id_cliente",
        ]
