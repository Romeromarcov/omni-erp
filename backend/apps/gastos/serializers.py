from rest_framework import serializers

from . import models


class CategoriaGastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CategoriaGasto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_categoria_gasto",
            "nombre_categoria",
            "descripcion",
            "id_cuenta_contable",
            "requiere_factura",
            "activo",
            "id_empresa",
        ]


class DetalleGastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DetalleGasto
        fields = [
            "id_detalle_gasto",
            "id_gasto",
            "id_cuenta_contable",
            "descripcion",
            "monto",
            "monto_iva",
        ]


class GastoSerializer(serializers.ModelSerializer):
    detalles = DetalleGastoSerializer(many=True, read_only=True)
    estado_gasto_display = serializers.CharField(source="get_estado_gasto_display", read_only=True)

    class Meta:
        model = models.Gasto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        # `estado_gasto`/`sin_respaldo` son read-only: solo cambian vía servicio
        # (aprobar/rechazar), nunca por PATCH directo (defensa de máquina de estados).
        fields = [
            "id_gasto",
            "fecha_gasto",
            "descripcion",
            "monto",
            "monto_iva",
            "tasa_cambio",
            "id_proveedor",
            "id_producto",
            "tiene_factura",
            "numero_factura",
            "sin_respaldo",
            "id_empleado_responsable",
            "id_empleado_responsable_temp",
            "estado_gasto",
            "estado_gasto_display",
            "id_usuario_registro",
            "id_usuario_registro_temp",
            "fecha_creacion",
            "id_empresa",
            "id_moneda",
            "id_categoria_gasto",
            "detalles",
        ]
        read_only_fields = ["estado_gasto", "sin_respaldo", "fecha_creacion"]


class ReembolsoGastoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ReembolsoGasto
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_reembolso",
            "id_empleado",
            "id_empleado_temp",
            "monto_reembolso",
            "fecha_reembolso",
            "estado_reembolso",
            "id_usuario_registro",
            "id_usuario_registro_temp",
            "fecha_creacion",
            "id_empresa",
            "id_gasto",
            "id_moneda",
            "id_metodo_pago",
        ]
