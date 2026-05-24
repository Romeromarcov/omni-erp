from rest_framework import serializers

from .models import Beneficio, BeneficioEmpleado, Cargo, Empleado, LicenciaEmpleado, TipoLicencia


class CargoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cargo
        fields = "__all__"


class EmpleadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Empleado
        fields = "__all__"


class BeneficioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Beneficio
        fields = "__all__"


class BeneficioEmpleadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = BeneficioEmpleado
        fields = "__all__"


class TipoLicenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoLicencia
        fields = "__all__"


class LicenciaEmpleadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenciaEmpleado
        fields = "__all__"
