from rest_framework import serializers

from . import models

# Serializadores para nomina.
# CTF-005 (fase 2 — dinero & nómina): cada serializer declara una whitelist
# explícita de campos para cerrar la superficie de asignación masiva (CWE-915)
# en datos de nómina (salarios, deducciones — PII sensible).


class PeriodoNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PeriodoNomina
        fields = [
            "id_periodo_nomina",
            "nombre_periodo",
            "fecha_inicio",
            "fecha_fin",
            "fecha_pago",
            "tipo_periodo",
            "estado",
            "observaciones",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]


class ConceptoNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ConceptoNomina
        fields = [
            "id_concepto_nomina",
            "codigo_concepto",
            "nombre_concepto",
            "tipo_concepto",
            "categoria",
            "formula_calculo",
            "es_fijo",
            "monto_fijo",
            "es_porcentaje",
            "porcentaje",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]


class ProcesoNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProcesoNomina
        fields = [
            "id_proceso_nomina",
            "numero_proceso",
            "fecha_proceso",
            "total_empleados",
            "total_devengado",
            "total_deducciones",
            "total_neto",
            "estado",
            "observaciones",
            "fecha_creacion",
            "id_empresa",
            "id_periodo_nomina",
        ]


class NominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Nomina
        fields = [
            "id_nomina",
            "sueldo_base",
            "total_devengado",
            "total_deducciones",
            "total_neto",
            "dias_trabajados",
            "horas_trabajadas",
            "horas_extras",
            "estado",
            "fecha_calculo",
            "observaciones",
            "id_proceso_nomina",
            "id_empleado",
        ]


class DetalleNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DetalleNomina
        fields = [
            "id_detalle_nomina",
            "cantidad",
            "valor_unitario",
            "valor_total",
            "observaciones",
            "id_nomina",
            "id_concepto_nomina",
        ]


class ProcesoNominaExtrasalarialSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProcesoNominaExtrasalarial
        fields = [
            "id_proceso_extrasalarial",
            "numero_proceso",
            "tipo_proceso",
            "fecha_proceso",
            "fecha_corte",
            "total_empleados",
            "total_monto",
            "estado",
            "observaciones",
            "fecha_creacion",
            "id_empresa",
        ]


class NominaExtrasalarialSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.NominaExtrasalarial
        fields = [
            "id_nomina_extrasalarial",
            "periodo_inicio",
            "periodo_fin",
            "salario_promedio",
            "dias_laborados",
            "monto_calculado",
            "deducciones",
            "monto_neto",
            "estado",
            "fecha_calculo",
            "observaciones",
            "id_proceso_extrasalarial",
            "id_empleado",
        ]
