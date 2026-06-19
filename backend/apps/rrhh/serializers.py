from rest_framework import serializers

from .models import Beneficio, BeneficioEmpleado, Cargo, Empleado, LicenciaEmpleado, TipoLicencia


class CargoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cargo
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "nombre",
            "descripcion",
            "activo",
            "empresa",
        ]


class EmpleadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Empleado
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "nombre",
            "apellido",
            "cedula",
            "fecha_ingreso",
            "activo",
            "empresa",
            "cargo",
            "contacto",
        ]


class BeneficioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Beneficio
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_beneficio",
            "nombre_beneficio",
            "descripcion",
            "tipo_beneficio",
            "monto_fijo",
            "porcentaje_salario",
            "es_obligatorio",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]


class BeneficioEmpleadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = BeneficioEmpleado
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_beneficio_empleado",
            "fecha_inicio",
            "fecha_fin",
            "monto_personalizado",
            "porcentaje_personalizado",
            "estado",
            "observaciones",
            "fecha_creacion",
            "id_empleado",
            "id_beneficio",
        ]


class TipoLicenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoLicencia
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_tipo_licencia",
            "nombre_tipo",
            "descripcion",
            "es_remunerada",
            "dias_maximos_por_año",
            "requiere_aprobacion",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]


class LicenciaEmpleadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenciaEmpleado
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_licencia",
            "fecha_inicio",
            "fecha_fin",
            "dias_solicitados",
            "motivo",
            "estado",
            "fecha_aprobacion",
            "observaciones_aprobacion",
            "fecha_creacion",
            "id_empleado",
            "id_tipo_licencia",
            "id_aprobador",
        ]
