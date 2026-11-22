"""Serializers OpenAPI de respuesta para el framework de localización (ADR-007)."""

from __future__ import annotations

from rest_framework import serializers


class PuertoLocalizacionEstadoSerializer(serializers.Serializer):
    """Estado de un puerto de localización resuelto para una empresa."""

    clase = serializers.CharField(read_only=True)
    es_noop = serializers.BooleanField(read_only=True)
    activo = serializers.BooleanField(read_only=True)


class EstadoLocalizacionResponseSerializer(serializers.Serializer):
    """Respuesta del endpoint de estado de localización de una empresa."""

    empresa_id = serializers.UUIDField(read_only=True)
    pais_codigo_iso = serializers.CharField(allow_null=True, allow_blank=True, read_only=True)
    pais_normalizado = serializers.CharField(allow_null=True, allow_blank=True, read_only=True)
    localizacion_legal_activa = serializers.BooleanField(read_only=True)
    localizacion_mercado_activa = serializers.BooleanField(read_only=True)
    puertos = serializers.DictField(
        child=PuertoLocalizacionEstadoSerializer(),
        read_only=True,
    )
