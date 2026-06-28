"""Serializers de conciliación (Fase 4).

``empresa`` nunca es writable (se inyecta en ``perform_create``). La
``ConciliacionLubrikca`` es de solo lectura: la produce el servicio; la API solo
la lista, la concilia (acción) y la marca revisada (acción).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.cxc_lubrikca.models import (
    ConciliacionLubrikca,
    ConfiguracionConciliacion,
)

_READ_ONLY = ("id", "created_at", "updated_at")


class ConfiguracionConciliacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionConciliacion
        fields = (
            "id",
            "tolerance_rounding",
            "tolerance_red",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY


class ConciliacionLubrikcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConciliacionLubrikca
        fields = (
            "id",
            "pedido",
            "total_motor",
            "monto_facturado",
            "ncs",
            "diferencia",
            "resultado",
            "revisado_por",
            "conciliado_en",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields  # solo lectura: la salida la produce el servicio


class ConciliarSerializer(serializers.Serializer):
    """Cuerpo de la acción ``conciliar`` (endpoint dedicado por pedido)."""

    pedido = serializers.UUIDField()
