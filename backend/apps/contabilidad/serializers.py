from rest_framework import serializers

from .models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas


class PlanCuentasSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanCuentas
        fields = "__all__"


class DetalleAsientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleAsiento
        fields = "__all__"


class AsientoContableSerializer(serializers.ModelSerializer):
    detalles = DetalleAsientoSerializer(many=True, read_only=True, source="detalleasiento_set")

    class Meta:
        model = AsientoContable
        fields = "__all__"

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
        fields = "__all__"

    def validate(self, data):
        """Las cuentas del mapeo deben pertenecer a la misma empresa del mapeo."""
        empresa = data.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        for campo in ("cuenta_debe", "cuenta_haber"):
            cuenta = data.get(campo) or getattr(self.instance, campo, None)
            if empresa is not None and cuenta is not None and cuenta.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({campo: "La cuenta no pertenece a la empresa del mapeo."})
        return data
