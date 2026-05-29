"""Serializers for CxC API."""
from decimal import Decimal
from rest_framework import serializers
from apps.cxc.models import (
    GestionCobranza, PlantillaCobranza, AcuerdoPago, CuotaAcuerdo,
    LoteFraccionado, VentaFraccionada,
)


class PlantillaCobranzaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantillaCobranza
        fields = ["id", "nombre", "canal", "asunto", "cuerpo", "activa", "created_at"]
        read_only_fields = ["id", "created_at"]


class GestionCobranzaSerializer(serializers.ModelSerializer):
    class Meta:
        model = GestionCobranza
        fields = [
            "id", "empresa", "cliente_id", "cliente_nombre", "orden_ref",
            "cxc", "canal", "resultado", "notas", "plantilla",
            "score", "fecha_gestion", "proxima_accion", "gestionado_por",
            "created_at",
        ]
        read_only_fields = ["id", "empresa", "score", "created_at"]


class CuotaAcuerdoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuotaAcuerdo
        fields = [
            "id", "numero_cuota", "fecha_vencimiento", "monto",
            "estado", "pago", "monto_pagado", "fecha_pago", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AcuerdoPagoSerializer(serializers.ModelSerializer):
    cuotas = CuotaAcuerdoSerializer(many=True, read_only=True)

    class Meta:
        model = AcuerdoPago
        fields = [
            "id", "empresa", "cliente_id", "cliente_nombre", "cxc", "gestion",
            "monto_total", "periodicidad", "plazo_total_dias", "fecha_inicio",
            "monto_cuota", "porcentaje_abono", "estado", "moneda_codigo",
            "observaciones", "cuotas", "created_at",
        ]
        read_only_fields = ["id", "empresa", "estado", "created_at"]


class AcuerdoPagoCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creation (no cuotas nested)."""
    class Meta:
        model = AcuerdoPago
        fields = [
            "cliente_id", "cliente_nombre", "cxc", "gestion",
            "monto_total", "periodicidad", "plazo_total_dias", "fecha_inicio",
            "monto_cuota", "porcentaje_abono", "moneda_codigo", "observaciones",
        ]


class LoteFraccionadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoteFraccionado
        fields = [
            "id", "empresa", "producto_id", "producto_nombre", "descripcion",
            "cantidad_inicial", "cantidad_actual", "unidad_base", "unidad_venta",
            "factor_conversion", "precio_venta_unit", "moneda_codigo", "estado",
            "created_at",
        ]
        read_only_fields = ["id", "empresa", "created_at"]


class VentaFraccionadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = VentaFraccionada
        fields = [
            "id", "empresa", "lote", "cliente_id", "cliente_nombre",
            "cantidad", "precio_unit", "monto_total", "moneda_codigo",
            "estado", "pago", "notas", "created_at",
        ]
        read_only_fields = ["id", "empresa", "estado", "created_at"]


class RegistrarPagoSerializer(serializers.Serializer):
    """Input para registrar pago de cuota."""
    cuota_id = serializers.UUIDField()
    monto = serializers.DecimalField(max_digits=18, decimal_places=4)
    metodo_pago_id = serializers.UUIDField()
    moneda_id = serializers.UUIDField()
    referencia = serializers.CharField(required=False, allow_blank=True)
    observaciones = serializers.CharField(required=False, allow_blank=True)
