"""Serializers CTF-005 (whitelist explícita) para Costos en Destino y 3-Way Matching."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.viewsets import get_empresa_primaria, get_empresas_visible

from .models import AsignacionCostoDestino, CostoDestino, LineaCostoDestino


def _empresa_efectiva(serializer) -> str | None:
    if getattr(serializer, "instance", None) is not None:
        return str(serializer.instance.id_empresa_id)
    request = serializer.context.get("request") if hasattr(serializer, "context") else None
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        prim = get_empresa_primaria(user)
        if prim is None:
            raise serializers.ValidationError({"id_empresa": "El usuario no tiene empresa asignada."})
        return str(prim.pk)
    return None


class LineaCostoDestinoSerializer(serializers.ModelSerializer):
    concepto_display = serializers.CharField(source="get_concepto_display", read_only=True)

    class Meta:
        model = LineaCostoDestino
        fields = [
            "id_linea_costo_destino",
            "id_empresa",
            "id_costo_destino",
            "concepto",
            "concepto_display",
            "descripcion",
            "monto",
            "id_factura_compra",
            "observaciones",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_empresa", "id_linea_costo_destino", "fecha_creacion", "fecha_actualizacion"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        costo = attrs.get("id_costo_destino") or getattr(self.instance, "id_costo_destino", None)
        emp = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        if emp is None and costo is not None:
            emp = costo.id_empresa
            attrs["id_empresa"] = emp
        if costo is not None and emp is not None and str(costo.id_empresa_id) != str(emp.pk):
            raise serializers.ValidationError({"id_costo_destino": "El costo en destino no pertenece a la empresa."})
        if costo is not None and costo.estado != "BORRADOR":
            raise serializers.ValidationError(
                {"id_costo_destino": f"No se pueden modificar líneas en estado {costo.estado}."}
            )
        fac = (
            attrs.get("id_factura_compra")
            if "id_factura_compra" in attrs
            else getattr(self.instance, "id_factura_compra", None)
        )
        if fac is not None and emp is not None and str(fac.id_empresa_id) != str(emp.pk):
            raise serializers.ValidationError({"id_factura_compra": "La factura no pertenece a la empresa."})
        return attrs


class AsignacionCostoDestinoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)

    class Meta:
        model = AsignacionCostoDestino
        fields = [
            "id_asignacion",
            "id_empresa",
            "id_costo_destino",
            "id_detalle_recepcion",
            "id_producto",
            "producto_nombre",
            "base_prorrateo",
            "porcentaje_prorrateo",
            "costo_adicional_total",
            "costo_adicional_unitario",
            "costo_unitario_anterior",
            "costo_unitario_nuevo",
            "fecha_creacion",
        ]
        read_only_fields = fields


class CostoDestinoSerializer(serializers.ModelSerializer):
    lineas = LineaCostoDestinoSerializer(many=True, read_only=True)
    asignaciones = AsignacionCostoDestinoSerializer(many=True, read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = CostoDestino
        fields = [
            "id_costo_destino",
            "id_empresa",
            "id_recepcion",
            "numero_documento",
            "fecha",
            "metodo_prorrateo",
            "ambito",
            "nro_expediente_impor",
            "nro_planilla_impor",
            "monto_total",
            "estado",
            "estado_display",
            "id_asiento",
            "observaciones",
            "activo",
            "lineas",
            "asignaciones",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_costo_destino",
            "id_empresa",
            "monto_total",
            "estado",
            "id_asiento",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request") if hasattr(self, "context") else None
        user = getattr(request, "user", None)
        visibles = (
            {str(pk) for pk in get_empresas_visible(user).values_list("pk", flat=True)}
            if user is not None and getattr(user, "is_authenticated", False)
            else None
        )
        recepcion = attrs.get("id_recepcion") or getattr(self.instance, "id_recepcion", None)
        emp = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        if emp is None and recepcion is not None:
            emp = recepcion.id_empresa
            attrs["id_empresa"] = emp
        emp_ref = str(emp.pk) if emp is not None else _empresa_efectiva(self)
        if emp is not None and visibles is not None and str(emp.pk) not in visibles:
            raise serializers.ValidationError({"id_empresa": "Empresa fuera de su alcance."})
        if recepcion is not None and emp_ref is not None and str(recepcion.id_empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_recepcion": "La recepción no pertenece a la empresa indicada."})
        return attrs


class ValidarThreeWayMatchingInputSerializer(serializers.Serializer):
    tolerancia_cantidad_pct = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, default=Decimal("0.00"), min_value=Decimal("0")
    )
    tolerancia_precio_pct = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, default=Decimal("1.00"), min_value=Decimal("0")
    )
