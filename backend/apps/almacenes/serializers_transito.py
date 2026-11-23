"""Serializers CTF-005 para Transferencias Inter-Almacén en Tránsito (Plan 09 Fase 5.4)."""

from __future__ import annotations

from rest_framework import serializers

from .models import DetalleTransferenciaTransito, TransferenciaTransito


class DetalleTransferenciaTransitoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)

    class Meta:
        model = DetalleTransferenciaTransito
        fields = [
            "id_detalle",
            "id_empresa",
            "id_transferencia",
            "id_producto",
            "producto_nombre",
            "id_variante",
            "cantidad_despachada",
            "cantidad_recibida",
            "costo_unitario",
            "fecha_creacion",
        ]
        read_only_fields = fields


class TransferenciaTransitoSerializer(serializers.ModelSerializer):
    detalles = DetalleTransferenciaTransitoSerializer(many=True, read_only=True)
    almacen_origen_nombre = serializers.CharField(source="id_almacen_origen.nombre_almacen", read_only=True)
    almacen_destino_nombre = serializers.CharField(source="id_almacen_destino.nombre_almacen", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = TransferenciaTransito
        fields = [
            "id_transferencia_transito",
            "id_empresa",
            "numero",
            "id_almacen_origen",
            "almacen_origen_nombre",
            "id_almacen_destino",
            "almacen_destino_nombre",
            "id_ubicacion_transito",
            "ambito",
            "estado",
            "estado_display",
            "fecha_despacho",
            "fecha_recepcion",
            "id_usuario_despacho",
            "id_usuario_recepcion",
            "observaciones",
            "activo",
            "detalles",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class _DetalleDespachoTransitoInputSerializer(serializers.Serializer):
    producto = serializers.UUIDField()
    variante = serializers.UUIDField(required=False, allow_null=True)
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4)


class DespacharTransferenciaTransitoInputSerializer(serializers.Serializer):
    id_almacen_origen = serializers.UUIDField()
    id_almacen_destino = serializers.UUIDField()
    id_ubicacion_transito = serializers.UUIDField(required=False, allow_null=True)
    ambito = serializers.ChoiceField(choices=["FISCAL", "GERENCIAL"], default="FISCAL", required=False)
    numero = serializers.CharField(max_length=50, required=False, allow_blank=True)
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    items = _DetalleDespachoTransitoInputSerializer(many=True)


class RecibirTransferenciaTransitoInputSerializer(serializers.Serializer):
    cantidades_recibidas = serializers.DictField(
        child=serializers.DecimalField(max_digits=18, decimal_places=4),
        required=False,
        default=dict,
    )
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
