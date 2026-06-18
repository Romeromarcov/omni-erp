from rest_framework import serializers

from . import models

# Serializadores para costos
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente


class CostoProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CostoProduccion
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_costo_produccion",
            "tipo_costo",
            "costo_unitario",
            "cantidad",
            "costo_total",
            "fecha_calculo",
            "observaciones",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_orden_produccion",
            "id_moneda",
        ]


class CostoEstandarProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CostoEstandarProducto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_costo_estandar",
            "tipo_costo",
            "costo_unitario_estandar",
            "fecha_vigencia_desde",
            "fecha_vigencia_hasta",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_producto",
            "id_moneda",
        ]


class AnalisisVariacionCostoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AnalisisVariacionCosto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_analisis_variacion",
            "tipo_costo",
            "costo_estandar",
            "costo_real",
            "variacion_cantidad",
            "variacion_precio",
            "variacion_total",
            "porcentaje_variacion",
            "tipo_variacion",
            "fecha_analisis",
            "observaciones",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_orden_produccion",
            "id_producto",
        ]
