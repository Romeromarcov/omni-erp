"""Serializers CTF-005 (whitelist explícita) para Logística TMS Inteligente (Plan 09 Fase 6)."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.viewsets import get_empresa_primaria, get_empresas_visible

from .models import Conductor, ParadaEntrega, RutaDespacho, TarifaFlete, Vehiculo, ZonaLogistica


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


class ZonaLogisticaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZonaLogistica
        fields = [
            "id_zona",
            "id_empresa",
            "codigo",
            "nombre",
            "ciudad",
            "estado_provincia",
            "centro_lat",
            "centro_lng",
            "radio_km",
            "tarifa_base_usd",
            "tiempo_servicio_min",
            "observaciones",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_zona", "id_empresa", "fecha_creacion", "fecha_actualizacion"]


class TarifaFleteSerializer(serializers.ModelSerializer):
    zona_nombre = serializers.CharField(source="id_zona.nombre", read_only=True)

    class Meta:
        model = TarifaFlete
        fields = [
            "id_tarifa",
            "id_empresa",
            "id_zona",
            "zona_nombre",
            "tipo_calculo",
            "monto_base_usd",
            "tarifa_unidad_usd",
            "minimo_usd",
            "moneda_referencia",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_tarifa", "id_empresa", "fecha_creacion", "fecha_actualizacion"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        zona = attrs.get("id_zona") or getattr(self.instance, "id_zona", None)
        emp_ref = _empresa_efectiva(self)
        if zona is not None and emp_ref is not None and str(zona.id_empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_zona": "La zona logística no pertenece a la empresa."})
        return attrs


class VehiculoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehiculo
        fields = [
            "id_vehiculo",
            "id_empresa",
            "placa",
            "marca_modelo",
            "tipo_vehiculo",
            "capacidad_kg",
            "capacidad_m3",
            "capacidad_paletas",
            "capacidad_litros",
            "velocidad_promedio_kmh",
            "estado",
            "latitud_actual",
            "longitud_actual",
            "gps_actualizado_en",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_vehiculo", "id_empresa", "gps_actualizado_en", "fecha_creacion", "fecha_actualizacion"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        lat = attrs.get("latitud_actual")
        lng = attrs.get("longitud_actual")
        if lat is not None and (lat < Decimal("-90") or lat > Decimal("90")):
            raise serializers.ValidationError({"latitud_actual": "Latitud fuera de rango [-90, 90]."})
        if lng is not None and (lng < Decimal("-180") or lng > Decimal("180")):
            raise serializers.ValidationError({"longitud_actual": "Longitud fuera de rango [-180, 180]."})
        if self.instance is not None and "estado" in attrs and self.instance.estado == "EN_RUTA":
            if attrs["estado"] != "EN_RUTA":
                raise serializers.ValidationError(
                    {"estado": "No se puede cambiar manualmente el estado de un vehículo EN_RUTA."}
                )
        return attrs


class ConductorSerializer(serializers.ModelSerializer):
    vehiculo_placa = serializers.CharField(source="id_vehiculo_asignado.placa", read_only=True)

    class Meta:
        model = Conductor
        fields = [
            "id_conductor",
            "id_empresa",
            "id_empleado",
            "id_usuario",
            "nombre_completo",
            "cedula",
            "telefono",
            "licencia_grado",
            "licencia_vence",
            "id_vehiculo_asignado",
            "vehiculo_placa",
            "disponible",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_conductor", "id_empresa", "fecha_creacion", "fecha_actualizacion"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        emp_ref = _empresa_efectiva(self)
        veh = attrs.get("id_vehiculo_asignado") or getattr(self.instance, "id_vehiculo_asignado", None)
        empl = attrs.get("id_empleado") or getattr(self.instance, "id_empleado", None)
        usr = attrs.get("id_usuario")
        if usr is None and "id_usuario" not in attrs and self.instance is not None:
            usr = self.instance.id_usuario
        if veh is not None and emp_ref is not None and str(veh.id_empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_vehiculo_asignado": "El vehículo no pertenece a la empresa."})
        if empl is not None and emp_ref is not None and str(empl.empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_empleado": "El empleado no pertenece a la empresa."})
        if (
            usr is not None
            and emp_ref is not None
            and not (getattr(usr, "es_superusuario_omni", False) or getattr(usr, "is_superuser", False))
            and not usr.empresas.filter(pk=emp_ref).exists()
        ):
            raise serializers.ValidationError({"id_usuario": "El usuario asignado no pertenece a la empresa."})
        return attrs


class ParadaEntregaSerializer(serializers.ModelSerializer):
    despacho_numero = serializers.CharField(source="id_despacho.numero_despacho", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = ParadaEntrega
        fields = [
            "id_parada",
            "id_empresa",
            "id_ruta",
            "id_despacho",
            "despacho_numero",
            "id_direccion_cliente",
            "secuencia",
            "estado",
            "estado_display",
            "latitud",
            "longitud",
            "direccion_texto",
            "distancia_tramo_km",
            "eta_estimada",
            "fecha_llegada_real",
            "token_tracking",
            "epod_receptor_nombre",
            "epod_receptor_cedula",
            "epod_firma_base64",
            "epod_foto_url",
            "epod_latitud",
            "epod_longitud",
            "epod_observaciones",
            "motivo_rechazo",
            "monto_cobrado_en_sitio",
            "id_pago_cobro",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class RutaDespachoSerializer(serializers.ModelSerializer):
    paradas = ParadaEntregaSerializer(many=True, read_only=True)
    vehiculo_placa = serializers.CharField(source="id_vehiculo.placa", read_only=True)
    conductor_nombre = serializers.CharField(source="id_conductor.nombre_completo", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = RutaDespacho
        fields = [
            "id_ruta",
            "id_empresa",
            "codigo",
            "fecha_ruta",
            "id_almacen_origen",
            "origen_lat",
            "origen_lng",
            "id_vehiculo",
            "vehiculo_placa",
            "id_conductor",
            "conductor_nombre",
            "id_zona",
            "estado",
            "estado_display",
            "distancia_estimada_km",
            "duracion_estimada_min",
            "peso_total_kg",
            "volumen_total_m3",
            "costo_flete_estimado_usd",
            "proveedor_delivery_externo",
            "referencia_delivery_externo",
            "tracking_url_externo",
            "id_guia_imprenta_digital",
            "guia_numero_control",
            "fecha_inicio",
            "fecha_fin",
            "observaciones",
            "paradas",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_ruta",
            "id_empresa",
            "estado",
            "distancia_estimada_km",
            "duracion_estimada_min",
            "peso_total_kg",
            "volumen_total_m3",
            "costo_flete_estimado_usd",
            "referencia_delivery_externo",
            "tracking_url_externo",
            "id_guia_imprenta_digital",
            "guia_numero_control",
            "fecha_inicio",
            "fecha_fin",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and self.instance.estado != "PLANIFICADA":
            raise serializers.ValidationError(
                {"estado": f"No se puede modificar una ruta en estado {self.instance.estado}."}
            )
        request = self.context.get("request") if hasattr(self, "context") else None
        user = getattr(request, "user", None)
        visibles = (
            {str(pk) for pk in get_empresas_visible(user).values_list("pk", flat=True)}
            if user is not None and getattr(user, "is_authenticated", False)
            else None
        )
        emp_ref = _empresa_efectiva(self)
        if emp_ref is not None and visibles is not None and emp_ref not in visibles:
            raise serializers.ValidationError({"id_empresa": "Empresa fuera de su alcance."})

        alm = attrs.get("id_almacen_origen") or getattr(self.instance, "id_almacen_origen", None)
        veh = attrs.get("id_vehiculo") or getattr(self.instance, "id_vehiculo", None)
        cond = attrs.get("id_conductor") or getattr(self.instance, "id_conductor", None)
        zona = attrs.get("id_zona") or getattr(self.instance, "id_zona", None)
        if alm is not None and emp_ref is not None and str(alm.id_empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_almacen_origen": "El almacén no pertenece a la empresa."})
        if veh is not None and emp_ref is not None and str(veh.id_empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_vehiculo": "El vehículo no pertenece a la empresa."})
        if cond is not None and emp_ref is not None and str(cond.id_empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_conductor": "El conductor no pertenece a la empresa."})
        if zona is not None and emp_ref is not None and str(zona.id_empresa_id) != emp_ref:
            raise serializers.ValidationError({"id_zona": "La zona no pertenece a la empresa."})
        return attrs


class ActualizarGPSVehiculoInputSerializer(serializers.Serializer):
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6)


class OptimizarVRPInputSerializer(serializers.Serializer):
    id_almacen_origen = serializers.UUIDField()
    despachos = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    vehiculos = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    origen_lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    origen_lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    fecha_ruta = serializers.DateField(required=False)
    factor_trafico = serializers.DecimalField(max_digits=4, decimal_places=2, required=False, default=Decimal("1.00"))
    id_zona = serializers.UUIDField(required=False, allow_null=True)


class CotizarDeliveryInputSerializer(serializers.Serializer):
    proveedor = serializers.ChoiceField(choices=["SIMULADO", "UBER_DIRECT", "RIDERY", "YUMMY"])
    origen_lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    origen_lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    destino_lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    destino_lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    peso_kg = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, default=Decimal("1.0000"))


class SolicitarDeliveryRutaInputSerializer(serializers.Serializer):
    proveedor = serializers.ChoiceField(choices=["SIMULADO", "UBER_DIRECT", "RIDERY", "YUMMY"])
    destino_lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    destino_lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    direccion_destino = serializers.CharField(max_length=500)


class EmitirGuiaSeniatInputSerializer(serializers.Serializer):
    proveedor = serializers.ChoiceField(choices=["SIMULADO", "UNIDIGITAL"], required=False, default="SIMULADO")


class CobroEnSitioInputSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=18, decimal_places=4)
    id_metodo_pago = serializers.UUIDField()
    id_moneda = serializers.UUIDField()
    tasa = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, default=Decimal("1.0000"))
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class RegistrarEPODInputSerializer(serializers.Serializer):
    resultado = serializers.ChoiceField(
        choices=["ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA"], required=False, default="ENTREGADA"
    )
    receptor_nombre = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    receptor_cedula = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    firma_base64 = serializers.CharField(required=False, allow_blank=True, default="")
    foto_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    motivo_rechazo = serializers.CharField(required=False, allow_blank=True, default="")
    cobro = CobroEnSitioInputSerializer(required=False, allow_null=True)
