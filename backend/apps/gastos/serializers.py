from rest_framework import serializers

from . import models

# Serializadores para gastos
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente


class CategoriaGastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CategoriaGasto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_categoria_gasto",
            "nombre_categoria",
            "descripcion",
            "activo",
            "id_empresa",
        ]


class GastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Gasto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_gasto",
            "fecha_gasto",
            "descripcion",
            "monto",
            "id_empleado_responsable_temp",
            "estado_gasto",
            "id_usuario_registro_temp",
            "fecha_creacion",
            "id_empresa",
            "id_moneda",
            "id_categoria_gasto",
        ]


class ReembolsoGastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ReembolsoGasto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_reembolso",
            "id_empleado_temp",
            "monto_reembolso",
            "fecha_reembolso",
            "estado_reembolso",
            "id_usuario_registro_temp",
            "fecha_creacion",
            "id_empresa",
            "id_gasto",
            "id_moneda",
            "id_metodo_pago",
        ]
