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

    def _empresas_visibles(self):
        from apps.core.viewsets import get_empresas_visible

        request = self.context.get("request")
        if request is None or not getattr(request, "user", None):
            return None
        return get_empresas_visible(request.user)

    def validate_cxc(self, value):
        """BUG-M3: el FK cxc debe pertenecer a una empresa visible del usuario."""
        if value is None:
            return value
        empresas = self._empresas_visibles()
        if (
            empresas is None
            or value.empresa_id is None
            or not empresas.filter(pk=value.empresa_id).exists()
        ):
            raise serializers.ValidationError(
                "La cuenta por cobrar indicada no existe o no pertenece a su empresa."
            )
        return value

    def validate_gestion(self, value):
        """Mismo aislamiento multi-tenant para el FK gestion."""
        if value is None:
            return value
        empresas = self._empresas_visibles()
        if empresas is None or not empresas.filter(pk=value.empresa_id).exists():
            raise serializers.ValidationError(
                "La gestión indicada no existe o no pertenece a su empresa."
            )
        return value

    def validate_monto_total(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto total debe ser mayor que cero.")
        return value

    def validate(self, attrs):
        """BUG-M3: coherencia cuota/total — las cuotas nunca pueden exceder el total."""
        monto_total = attrs.get("monto_total")
        monto_cuota = attrs.get("monto_cuota")
        porcentaje_abono = attrs.get("porcentaje_abono")

        if monto_cuota is not None and porcentaje_abono is not None:
            raise serializers.ValidationError(
                "Indique monto_cuota o porcentaje_abono, no ambos."
            )
        if monto_cuota is not None:
            if monto_cuota <= 0:
                raise serializers.ValidationError(
                    {"monto_cuota": "El monto de la cuota debe ser mayor que cero."}
                )
            if monto_total is not None and monto_cuota > monto_total:
                raise serializers.ValidationError(
                    {"monto_cuota": "El monto de la cuota no puede exceder el monto total."}
                )
        if porcentaje_abono is not None and not (
            Decimal("0") < porcentaje_abono <= Decimal("100")
        ):
            raise serializers.ValidationError(
                {"porcentaje_abono": "El porcentaje de abono debe estar entre 0 y 100."}
            )
        return attrs


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
    # BUG-A2: min_value > 0 — un pago de monto cero o negativo no es válido.
    monto = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )
    metodo_pago_id = serializers.UUIDField()
    moneda_id = serializers.UUIDField()
    referencia = serializers.CharField(required=False, allow_blank=True)
    observaciones = serializers.CharField(required=False, allow_blank=True)
