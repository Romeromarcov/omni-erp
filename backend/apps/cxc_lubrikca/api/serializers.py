"""Serializers de la configuración del motor CxC Lubrikca (Fase 1).

Un ``ModelSerializer`` por modelo. ``empresa`` NO se expone como writable: se
inyecta en ``perform_create`` (H-API-1). Validaciones comunes:
- ``vigencia_hasta >= vigencia_desde`` cuando ambas están presentes;
- ``porcentaje >= 0``.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.cxc_lubrikca.models import (
    DescuentoBCVCompleto,
    DescuentoMarcaCategoria,
    Feriado,
    MetodoPago,
    PromocionPrimeraCompra,
    ReglaRecurrencia,
)

_READ_ONLY = ("id", "created_at", "updated_at")


class _VigenciaValidationMixin:
    """Valida la ventana de vigencia (hasta >= desde) cuando ambas existen."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        desde = attrs.get("vigencia_desde")
        hasta = attrs.get("vigencia_hasta")
        if desde is None and self.instance is not None:
            desde = self.instance.vigencia_desde
        if hasta is None and self.instance is not None and "vigencia_hasta" not in attrs:
            hasta = self.instance.vigencia_hasta
        if desde is not None and hasta is not None and hasta < desde:
            raise serializers.ValidationError(
                {"vigencia_hasta": "Debe ser mayor o igual a vigencia_desde."}
            )
        return attrs


class DescuentoMarcaCategoriaSerializer(_VigenciaValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = DescuentoMarcaCategoria
        fields = (
            "id",
            "marca",
            "categoria",
            "tipo_descuento",
            "porcentaje",
            "vigencia_desde",
            "vigencia_hasta",
            "activo",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY

    def validate_porcentaje(self, value):
        if value < 0:
            raise serializers.ValidationError("El porcentaje no puede ser negativo.")
        return value


class DescuentoBCVCompletoSerializer(_VigenciaValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = DescuentoBCVCompleto
        fields = (
            "id",
            "porcentaje",
            "vigencia_desde",
            "vigencia_hasta",
            "activo",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY

    def validate_porcentaje(self, value):
        if value < 0:
            raise serializers.ValidationError("El porcentaje no puede ser negativo.")
        return value


class PromocionPrimeraCompraSerializer(_VigenciaValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = PromocionPrimeraCompra
        fields = (
            "id",
            "producto",
            "vigencia_desde",
            "vigencia_hasta",
            "activo",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY


class ReglaRecurrenciaSerializer(_VigenciaValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = ReglaRecurrencia
        fields = (
            "id",
            "condicion",
            "tipo_beneficio",
            "valor",
            "vigencia_desde",
            "vigencia_hasta",
            "activo",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY

    def validate_valor(self, value):
        if value < 0:
            raise serializers.ValidationError("El valor no puede ser negativo.")
        return value


class FeriadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feriado
        fields = (
            "id",
            "fecha",
            "descripcion",
            "tipo",
            "activo",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY


class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = (
            "id",
            "codigo",
            "nombre",
            "moneda",
            "tipo_tasa",
            "es_contado",
            "activo",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY
