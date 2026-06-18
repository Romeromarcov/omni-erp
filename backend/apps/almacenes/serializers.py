from rest_framework import serializers

from .models import Almacen, UbicacionAlmacen


class AlmacenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Almacen
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_almacen",
            "nombre_almacen",
            "codigo_almacen",
            "direccion",
            "referencia_externa",
            "documento_json",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_sucursal",
        ]


class UbicacionAlmacenSerializer(serializers.ModelSerializer):
    class Meta:
        model = UbicacionAlmacen
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_ubicacion",
            "codigo_ubicacion",
            "nombre_ubicacion",
            "tipo_ubicacion",
            "pasillo",
            "estante",
            "nivel",
            "posicion",
            "capacidad_maxima",
            "unidad_capacidad",
            "temperatura_minima",
            "temperatura_maxima",
            "activo",
            "requiere_autorizacion",
            "observaciones",
            "fecha_creacion",
            "id_empresa",
            "id_almacen",
        ]
