from rest_framework import serializers

from apps.core.serializers import BaseModelSerializer

from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion, TipoAprobacion


class TipoAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = TipoAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_tipo_aprobacion",
            "codigo_tipo",
            "nombre_tipo",
            "descripcion",
            "modulo_origen",
            "activo",
            "id_empresa",
        ]


class FlujoAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = FlujoAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_flujo_aprobacion",
            "orden_etapa",
            "nombre_etapa",
            "monto_minimo",
            "monto_maximo",
            "activo",
            "id_tipo_aprobacion",
            "id_departamento",
            "rol_aprobador",
            "id_usuario_aprobador",
            "sla_horas",
            "escalar_a_rol",
            "escalar_a_usuario",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        tipo = attrs.get("id_tipo_aprobacion") or getattr(self.instance, "id_tipo_aprobacion", None)
        if tipo is None:
            return attrs

        empresa_id = tipo.id_empresa_id
        departamento = attrs.get("id_departamento")
        if departamento is not None and str(departamento.id_empresa_id) != str(empresa_id):
            raise serializers.ValidationError(
                {"id_departamento": "El departamento no pertenece a la empresa del tipo de aprobación."}
            )

        rol = attrs.get("rol_aprobador")
        if rol is not None and rol.id_empresa_id is not None and str(rol.id_empresa_id) != str(empresa_id):
            raise serializers.ValidationError(
                {"rol_aprobador": "El rol aprobador no pertenece a la empresa del tipo de aprobación."}
            )

        escalar_rol = attrs.get("escalar_a_rol")
        if (
            escalar_rol is not None
            and escalar_rol.id_empresa_id is not None
            and str(escalar_rol.id_empresa_id) != str(empresa_id)
        ):
            raise serializers.ValidationError(
                {"escalar_a_rol": "El rol de escalación no pertenece a la empresa del tipo de aprobación."}
            )

        usuario = attrs.get("id_usuario_aprobador")
        if usuario is not None and not usuario.empresas.filter(pk=empresa_id).exists():
            raise serializers.ValidationError(
                {"id_usuario_aprobador": "El usuario aprobador no pertenece a la empresa del tipo de aprobación."}
            )

        escalar_usuario = attrs.get("escalar_a_usuario")
        if escalar_usuario is not None and not escalar_usuario.empresas.filter(pk=empresa_id).exists():
            raise serializers.ValidationError(
                {"escalar_a_usuario": "El usuario de escalación no pertenece a la empresa del tipo de aprobación."}
            )

        monto_min = attrs.get("monto_minimo", getattr(self.instance, "monto_minimo", None))
        monto_max = attrs.get("monto_maximo", getattr(self.instance, "monto_maximo", None))
        if monto_min is not None and monto_max is not None and monto_min > monto_max:
            raise serializers.ValidationError({"monto_maximo": "El monto máximo no puede ser menor al monto mínimo."})

        return attrs


class SolicitudAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = SolicitudAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_solicitud_aprobacion",
            "id_entidad_origen",
            "nombre_modelo_origen",
            "fecha_solicitud",
            "estado_solicitud",
            "comentarios_solicitante",
            "fecha_ultima_actualizacion",
            "id_tipo_aprobacion",
            "id_departamento",
            "id_usuario_solicitante",
            "etapa_actual_flujo",
            "monto",
            "fecha_inicio_etapa",
            "escalada",
            "fecha_escalacion",
        ]
        # estado/etapa/monto/SLA los gobierna el servicio (crear_solicitud /
        # registrar_decision / escalar_solicitudes_vencidas), nunca un PATCH directo.
        read_only_fields = [
            "estado_solicitud",
            "etapa_actual_flujo",
            "monto",
            "id_departamento",
            "fecha_inicio_etapa",
            "escalada",
            "fecha_escalacion",
        ]


class RegistroAprobacionSerializer(BaseModelSerializer):
    class Meta:
        model = RegistroAprobacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_registro_aprobacion",
            "fecha_decision",
            "tipo_decision",
            "comentarios",
            "id_solicitud_aprobacion",
            "id_flujo_aprobacion_etapa",
            "id_usuario_aprobador",
        ]


class DecidirSolicitudInputSerializer(serializers.Serializer):
    aprobado = serializers.BooleanField()
    comentarios = serializers.CharField(required=False, allow_blank=True, default="")
