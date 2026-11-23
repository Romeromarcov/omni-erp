"""Serializers CTF-005 (whitelist explícita) para Conteo Físico, Semáforo y Barcode."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.viewsets import get_empresa_primaria, get_empresas_visible, validar_uuid_param

from .models import ConteoInventario, LineaConteoInventario


class LineaConteoInventarioSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)
    producto_sku = serializers.CharField(source="id_producto.sku", read_only=True)
    codigo_barras = serializers.CharField(source="id_producto.codigo_barras", read_only=True)

    class Meta:
        model = LineaConteoInventario
        fields = [
            "id_linea_conteo",
            "id_empresa",
            "id_conteo",
            "id_producto",
            "producto_nombre",
            "producto_sku",
            "codigo_barras",
            "id_variante",
            "id_ubicacion",
            "cantidad_sistema",
            "cantidad_contada",
            "diferencia",
            "costo_unitario_referencia",
            "valor_diferencia",
            "conteos_escaneados",
            "observaciones",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class ConteoInventarioSerializer(serializers.ModelSerializer):
    lineas = LineaConteoInventarioSerializer(many=True, read_only=True)
    almacen_nombre = serializers.CharField(source="id_almacen.nombre_almacen", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = ConteoInventario
        fields = [
            "id_conteo",
            "id_empresa",
            "numero",
            "id_almacen",
            "almacen_nombre",
            "ambito",
            "tipo_conteo",
            "estado",
            "estado_display",
            "fecha_conteo",
            "id_responsable",
            "id_aprobador",
            "fecha_aprobacion",
            "observaciones",
            "activo",
            "lineas",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class ConteoLineaInicialInputSerializer(serializers.Serializer):
    producto = serializers.UUIDField()
    variante = serializers.UUIDField(required=False, allow_null=True)
    ubicacion = serializers.UUIDField(required=False, allow_null=True)


class CrearConteoInventarioInputSerializer(serializers.Serializer):
    id_almacen = serializers.UUIDField()
    tipo_conteo = serializers.ChoiceField(
        choices=[c[0] for c in ConteoInventario.TIPOS], default="CICLICO", required=False
    )
    ambito = serializers.ChoiceField(choices=["FISCAL", "GERENCIAL"], default="FISCAL", required=False)
    fecha_conteo = serializers.DateField(required=False)
    numero = serializers.CharField(max_length=50, required=False, allow_blank=True)
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    items = ConteoLineaInicialInputSerializer(many=True, required=False)


class EscanearConteoInputSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=100)
    cantidad = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, default=Decimal("1"), min_value=Decimal("0")
    )
    modo = serializers.ChoiceField(choices=["INCREMENTAL", "REEMPLAZAR"], required=False, default="INCREMENTAL")
    variante = serializers.UUIDField(required=False, allow_null=True)
    ubicacion = serializers.UUIDField(required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")


class EscanearOperacionInputSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=100)
    cantidad = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, default=Decimal("1"), min_value=Decimal("0.0001")
    )


def resolver_empresa_usuario_inventario(request, raw_empresa_id=None):
    visibles = get_empresas_visible(request.user)
    if raw_empresa_id:
        uid = validar_uuid_param(str(raw_empresa_id), "id_empresa")
        emp = visibles.filter(pk=uid).first()
        if emp is None:
            raise serializers.ValidationError({"id_empresa": "Empresa fuera de su alcance."})
        return emp
    emp = get_empresa_primaria(request.user) or visibles.first()
    if emp is None:
        raise serializers.ValidationError({"id_empresa": "El usuario no tiene empresa asignada."})
    return emp
