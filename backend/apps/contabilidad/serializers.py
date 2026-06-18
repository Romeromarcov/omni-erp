from rest_framework import serializers

from .models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas


class PlanCuentasSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanCuentas
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_cuenta_contable",
            "codigo_cuenta",
            "nombre_cuenta",
            "tipo_cuenta",
            "naturaleza",
            "nivel",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_cuenta_padre",
        ]


class DetalleAsientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleAsiento
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_asiento",
            "debe",
            "haber",
            "descripcion_detalle",
            "fecha_creacion",
            "id_asiento",
            "id_cuenta_contable",
        ]


class AsientoContableSerializer(serializers.ModelSerializer):
    detalles = DetalleAsientoSerializer(many=True, read_only=True, source="detalleasiento_set")

    class Meta:
        model = AsientoContable
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_asiento",
            "detalles",
            "fecha_asiento",
            "numero_asiento",
            "descripcion",
            "id_documento_origen",
            "nombre_modelo_origen",
            "estado_asiento",
            "id_usuario_registro_temp",
            "fecha_creacion",
            "id_empresa",
        ]

    def validate(self, data):
        """Validación personalizada para asientos contables"""
        # Aquí podrías agregar validaciones como que el asiento cuadre (debe = haber)
        return data


class MapeoContableSerializer(serializers.ModelSerializer):
    """
    Mapeo tipo de asiento → cuentas (workstream F). Sin la fila correspondiente,
    `generar_asiento_o_fallar()` responde 422 ("falta mapeo X") en los flujos
    automáticos (CAMBIO_DIVISA, FACTURA_VENTA, …).
    """

    tipo_asiento_display = serializers.CharField(source="get_tipo_asiento_display", read_only=True)
    cuenta_debe_nombre = serializers.CharField(source="cuenta_debe.nombre_cuenta", read_only=True)
    cuenta_haber_nombre = serializers.CharField(source="cuenta_haber.nombre_cuenta", read_only=True)

    class Meta:
        model = MapeoContable
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_mapeo",
            "tipo_asiento_display",
            "cuenta_debe_nombre",
            "cuenta_haber_nombre",
            "tipo_asiento",
            "descripcion_plantilla",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "cuenta_debe",
            "cuenta_haber",
        ]

    def validate(self, data):
        """Las cuentas del mapeo deben pertenecer a la misma empresa del mapeo."""
        empresa = data.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        for campo in ("cuenta_debe", "cuenta_haber"):
            cuenta = data.get(campo) or getattr(self.instance, campo, None)
            if empresa is not None and cuenta is not None and cuenta.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({campo: "La cuenta no pertenece a la empresa del mapeo."})
        return data
