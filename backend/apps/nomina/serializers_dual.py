"""Serializadores CTF-005 whitelisted para Nómina Dual VE (Plan 09 Ola 3B)."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.models import Empresa
from apps.rrhh.models import Empleado

from .models import DispersionPagoNomina, FichaSalarialDual, PrestamoEmpleado


def _validar_empresa_empleado(attrs: dict, instance=None) -> dict:
    empresa = attrs.get("id_empresa") or getattr(instance, "id_empresa", None)
    empleado = attrs.get("id_empleado") or getattr(instance, "id_empleado", None)
    if empresa is not None and empleado is not None and empleado.empresa_id != empresa.pk:
        raise serializers.ValidationError({"id_empleado": "El empleado no pertenece a la empresa seleccionada."})
    return attrs


class FichaSalarialDualSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.SerializerMethodField(read_only=True)
    empleado_cedula = serializers.CharField(source="id_empleado.cedula", read_only=True)

    class Meta:
        model = FichaSalarialDual
        fields = [
            "id_ficha",
            "id_empresa",
            "id_empleado",
            "empleado_nombre",
            "empleado_cedula",
            "salario_base_formal_ves",
            "cestaticket_mensual_ves",
            "porcentaje_ari",
            "cargas_familiares",
            "banco_formal",
            "cuenta_bancaria_formal",
            "tipo_cuenta_formal",
            "paquete_objetivo_mensual",
            "moneda_paquete",
            "bono_fijo_gerencial",
            "canal_pago_gerencial",
            "referencia_pago_gerencial",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_ficha", "empleado_nombre", "empleado_cedula", "fecha_creacion", "fecha_actualizacion"]

    def get_empleado_nombre(self, obj: FichaSalarialDual) -> str:
        return f"{obj.id_empleado.nombre} {obj.id_empleado.apellido}".strip()

    def validate(self, attrs: dict) -> dict:
        return _validar_empresa_empleado(attrs, instance=self.instance)


class PrestamoEmpleadoSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PrestamoEmpleado
        fields = [
            "id_prestamo",
            "id_empresa",
            "id_empleado",
            "empleado_nombre",
            "ambito_descuento",
            "moneda",
            "monto_principal",
            "cuotas_totales",
            "cuotas_pagadas",
            "monto_cuota",
            "saldo_pendiente",
            "fecha_otorgamiento",
            "estado",
            "observaciones",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_prestamo",
            "empleado_nombre",
            "cuotas_pagadas",
            "estado",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def get_empleado_nombre(self, obj: PrestamoEmpleado) -> str:
        return f"{obj.id_empleado.nombre} {obj.id_empleado.apellido}".strip()

    def validate(self, attrs: dict) -> dict:
        _validar_empresa_empleado(attrs, instance=self.instance)
        principal = attrs.get("monto_principal", getattr(self.instance, "monto_principal", None))
        saldo = attrs.get("saldo_pendiente", getattr(self.instance, "saldo_pendiente", None))
        if principal is not None and saldo is not None and saldo > principal:
            raise serializers.ValidationError({"saldo_pendiente": "El saldo no puede exceder el monto principal."})
        return attrs


class DispersionPagoNominaSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.SerializerMethodField(read_only=True)
    empleado_cedula = serializers.CharField(source="id_empleado.cedula", read_only=True)

    class Meta:
        model = DispersionPagoNomina
        fields = [
            "id_dispersion",
            "id_empresa",
            "id_proceso_nomina",
            "id_nomina",
            "id_empleado",
            "empleado_nombre",
            "empleado_cedula",
            "ambito",
            "canal_pago",
            "moneda",
            "monto",
            "desglose_denominaciones",
            "referencia_destino",
            "estado",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields

    def get_empleado_nombre(self, obj: DispersionPagoNomina) -> str:
        return f"{obj.id_empleado.nombre} {obj.id_empleado.apellido}".strip()


class ProcesarNominaDualInputSerializer(serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    id_periodo_nomina = serializers.UUIDField(required=True)
    tasa_bcv = serializers.DecimalField(max_digits=18, decimal_places=8, required=False, allow_null=True)
    incluir_asistencia = serializers.BooleanField(required=False, default=True)
    amortizar_prestamos = serializers.BooleanField(required=False, default=True)
    generar_dispersion = serializers.BooleanField(required=False, default=True)
    empleados = serializers.DictField(child=serializers.DictField(), required=False, default=dict)


class SimularLiquidacionInputSerializer(serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    id_empleado = serializers.IntegerField(required=True, min_value=1)
    salario_mensual_integral = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.01"))
    fecha_egreso = serializers.DateField(required=True)
    dias_vacaciones_pendientes = serializers.IntegerField(required=False, default=0, min_value=0)
    despido_injustificado = serializers.BooleanField(required=False, default=False)
    tasa_interes_prestaciones = serializers.DecimalField(
        max_digits=6, decimal_places=4, required=False, default=Decimal("0.1800"), min_value=Decimal("0")
    )


__all__ = [
    "DispersionPagoNominaSerializer",
    "Empleado",
    "Empresa",
    "FichaSalarialDualSerializer",
    "PrestamoEmpleadoSerializer",
    "ProcesarNominaDualInputSerializer",
    "SimularLiquidacionInputSerializer",
]
