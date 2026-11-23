from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from drf_yasg.utils import swagger_serializer_method
from rest_framework import serializers

from .models import (
    AsientoContable,
    CentroCosto,
    DetalleAsiento,
    DiarioContable,
    MapeoContable,
    PeriodoContable,
    PlanCuentas,
)


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


class DiarioContableSerializer(serializers.ModelSerializer):
    """Diario contable (estilo ``account.journal``) con validación de pertenencia por empresa."""

    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    ambito_display = serializers.CharField(source="get_ambito_display", read_only=True)
    cuenta_defecto_debe_nombre = serializers.CharField(
        source="cuenta_defecto_debe.nombre_cuenta",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )
    cuenta_defecto_haber_nombre = serializers.CharField(
        source="cuenta_defecto_haber.nombre_cuenta",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = DiarioContable
        fields = [
            "id_diario",
            "id_empresa",
            "codigo",
            "nombre",
            "tipo",
            "tipo_display",
            "ambito",
            "ambito_display",
            "prefijo_secuencia",
            "siguiente_numero",
            "cuenta_defecto_debe",
            "cuenta_defecto_debe_nombre",
            "cuenta_defecto_haber",
            "cuenta_defecto_haber_nombre",
            "id_cuenta_bancaria",
            "id_caja",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_diario", "fecha_creacion", "fecha_actualizacion"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        empresa = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        siguiente = attrs.get("siguiente_numero")
        if siguiente is not None and siguiente < 1:
            raise serializers.ValidationError({"siguiente_numero": "El siguiente número debe ser mayor o igual a 1."})

        if empresa is not None:
            for campo in ("cuenta_defecto_debe", "cuenta_defecto_haber"):
                cuenta = attrs.get(campo) if campo in attrs else getattr(self.instance, campo, None)
                if cuenta is not None and cuenta.id_empresa_id != empresa.pk:
                    raise serializers.ValidationError({campo: "La cuenta no pertenece a la empresa del diario."})

            cta_bancaria = (
                attrs.get("id_cuenta_bancaria")
                if "id_cuenta_bancaria" in attrs
                else getattr(self.instance, "id_cuenta_bancaria", None)
            )
            if cta_bancaria is not None and cta_bancaria.id_empresa_id != empresa.pk:
                raise serializers.ValidationError(
                    {"id_cuenta_bancaria": "La cuenta bancaria no pertenece a la empresa del diario."}
                )

            caja = attrs.get("id_caja") if "id_caja" in attrs else getattr(self.instance, "id_caja", None)
            if caja is not None and caja.empresa_id is not None and caja.empresa_id != empresa.pk:
                raise serializers.ValidationError({"id_caja": "La caja no pertenece a la empresa del diario."})

        return attrs


class CentroCostoSerializer(serializers.ModelSerializer):
    """Centro de costo analítico con validación multi-tenant y jerarquía acíclica."""

    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    padre_nombre = serializers.CharField(
        source="id_padre.nombre",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = CentroCosto
        fields = [
            "id_centro_costo",
            "id_empresa",
            "codigo",
            "nombre",
            "tipo",
            "tipo_display",
            "id_padre",
            "padre_nombre",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_centro_costo", "fecha_creacion", "fecha_actualizacion"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        empresa = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        if isinstance(self.instance, CentroCosto) and "id_empresa" in attrs:
            if attrs["id_empresa"].pk != self.instance.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_empresa": "No se puede cambiar la empresa de un centro de costo."}
                )
        padre = attrs.get("id_padre") if "id_padre" in attrs else getattr(self.instance, "id_padre", None)
        if padre is not None:
            if empresa is not None and padre.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({"id_padre": "El centro de costo padre no pertenece a la empresa."})
            actual: CentroCosto | None = padre
            visitados: set[Any] = {self.instance.pk} if isinstance(self.instance, CentroCosto) else set()
            while actual is not None:
                if actual.pk in visitados:
                    raise serializers.ValidationError(
                        {"id_padre": "La jerarquía de centros de costo no puede contener ciclos."}
                    )
                visitados.add(actual.pk)
                actual = actual.id_padre
        return attrs


class DetalleAsientoSerializer(serializers.ModelSerializer):
    contacto_nombre = serializers.CharField(
        source="id_contacto.nombre_completo",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )
    centro_costo_nombre = serializers.CharField(
        source="id_centro_costo.nombre",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = DetalleAsiento
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_asiento",
            "debe",
            "haber",
            "debe_base",
            "haber_base",
            "debe_pais",
            "haber_pais",
            "debe_referencia",
            "haber_referencia",
            "tasa_bcv_aplicada",
            "tasa_referencia_aplicada",
            "descripcion_detalle",
            "fecha_creacion",
            "id_asiento",
            "id_cuenta_contable",
            "id_contacto",
            "contacto_nombre",
            "id_centro_costo",
            "centro_costo_nombre",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        asiento = attrs.get("id_asiento") or getattr(self.instance, "id_asiento", None)
        contacto = attrs.get("id_contacto") if "id_contacto" in attrs else getattr(self.instance, "id_contacto", None)
        centro = (
            attrs.get("id_centro_costo")
            if "id_centro_costo" in attrs
            else getattr(self.instance, "id_centro_costo", None)
        )
        cuenta = (
            attrs.get("id_cuenta_contable")
            if "id_cuenta_contable" in attrs
            else getattr(self.instance, "id_cuenta_contable", None)
        )
        if asiento is not None:
            if cuenta is not None and cuenta.id_empresa_id != asiento.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_cuenta_contable": "La cuenta contable no pertenece a la empresa del asiento."}
                )
            if contacto is not None and contacto.id_empresa_id != asiento.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_contacto": "El contacto no pertenece a la empresa del asiento."}
                )
            if centro is not None and centro.id_empresa_id != asiento.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_centro_costo": "El centro de costo no pertenece a la empresa del asiento."}
                )
        return attrs


class AsientoContableSerializer(serializers.ModelSerializer):
    detalles = DetalleAsientoSerializer(many=True, read_only=True, source="detalleasiento_set")
    ambito_display = serializers.CharField(source="get_ambito_display", read_only=True)
    diario_nombre = serializers.CharField(
        source="id_diario.nombre",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )
    contra_asiento_id = serializers.SerializerMethodField()

    class Meta:
        model = AsientoContable
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_asiento",
            "detalles",
            "ambito",
            "ambito_display",
            "fecha_asiento",
            "numero_asiento",
            "descripcion",
            "id_documento_origen",
            "nombre_modelo_origen",
            "estado_asiento",
            "id_usuario_registro",
            "id_usuario_registro_temp",
            "fecha_creacion",
            "id_empresa",
            "id_diario",
            "diario_nombre",
            "asiento_revertido",
            "contra_asiento_id",
            "es_cierre",
        ]
        read_only_fields = ["id_asiento", "asiento_revertido", "es_cierre", "fecha_creacion"]

    @swagger_serializer_method(serializer_or_field=serializers.UUIDField(allow_null=True))
    def get_contra_asiento_id(self, obj: AsientoContable) -> str | None:
        try:
            contra = obj.contra_asiento
        except ObjectDoesNotExist:
            return None
        return str(contra.pk) if contra is not None else None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Valida pertenencia del diario a la empresa del asiento."""
        empresa = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        diario = attrs.get("id_diario") if "id_diario" in attrs else getattr(self.instance, "id_diario", None)
        if empresa is not None and diario is not None and diario.id_empresa_id != empresa.pk:
            raise serializers.ValidationError({"id_diario": "El diario no pertenece a la empresa del asiento."})
        return attrs


class MapeoContableSerializer(serializers.ModelSerializer):
    """
    Mapeo tipo de asiento → cuentas (workstream F). Sin la fila correspondiente,
    `generar_asiento_o_fallar()` responde 422 ("falta mapeo X") en los flujos
    automáticos (CAMBIO_DIVISA, FACTURA_VENTA, …).
    """

    tipo_asiento_display = serializers.CharField(source="get_tipo_asiento_display", read_only=True)
    cuenta_debe_nombre = serializers.CharField(source="cuenta_debe.nombre_cuenta", read_only=True)
    cuenta_haber_nombre = serializers.CharField(source="cuenta_haber.nombre_cuenta", read_only=True)
    diario_nombre = serializers.CharField(
        source="id_diario.nombre",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )

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
            "id_diario",
            "diario_nombre",
            "cuenta_debe",
            "cuenta_haber",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Las cuentas y el diario del mapeo deben pertenecer a la misma empresa del mapeo."""
        empresa = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        for campo in ("cuenta_debe", "cuenta_haber"):
            cuenta = attrs.get(campo) or getattr(self.instance, campo, None)
            if empresa is not None and cuenta is not None and cuenta.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({campo: "La cuenta no pertenece a la empresa del mapeo."})
        diario = attrs.get("id_diario") if "id_diario" in attrs else getattr(self.instance, "id_diario", None)
        if empresa is not None and diario is not None and diario.id_empresa_id != empresa.pk:
            raise serializers.ValidationError({"id_diario": "El diario no pertenece a la empresa del mapeo."})
        return attrs


class PeriodoContableSerializer(serializers.ModelSerializer):
    """Período contable mensual con trazabilidad de cierre y enlace al cierre anual."""

    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    asiento_cierre_numero = serializers.CharField(
        source="asiento_cierre.numero_asiento",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )
    cerrado_por_username = serializers.CharField(
        source="cerrado_por.username",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = PeriodoContable
        fields = [
            "id_periodo",
            "id_empresa",
            "anio",
            "mes",
            "estado",
            "estado_display",
            "fecha_cierre",
            "cerrado_por",
            "cerrado_por_username",
            "asiento_cierre",
            "asiento_cierre_numero",
            "observaciones",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_periodo",
            "estado",
            "fecha_cierre",
            "cerrado_por",
            "asiento_cierre",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        anio = attrs.get("anio", getattr(self.instance, "anio", None))
        mes = attrs.get("mes", getattr(self.instance, "mes", None))
        if anio is not None and (anio < 1900 or anio > 2100):
            raise serializers.ValidationError({"anio": "El año contable debe estar entre 1900 y 2100."})
        if mes is not None and (mes < 1 or mes > 12):
            raise serializers.ValidationError({"mes": "El mes debe estar entre 1 y 12."})
        return attrs


class RevertirAsientoInputSerializer(serializers.Serializer):
    """Payload de entrada para ``POST /api/contabilidad/asientos-contables/{id}/revertir/``."""

    fecha_reversion = serializers.DateField(required=False, allow_null=True)
    motivo = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CerrarPeriodoInputSerializer(serializers.Serializer):
    """Payload de entrada para ``POST /api/contabilidad/periodos-contables/cerrar/``."""

    id_empresa = serializers.UUIDField()
    anio = serializers.IntegerField(min_value=1900, max_value=2100)
    mes = serializers.IntegerField(min_value=1, max_value=12)
    observaciones = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class CerrarPeriodoDetalleInputSerializer(serializers.Serializer):
    """Payload de entrada para ``POST /api/contabilidad/periodos-contables/{id}/cerrar/``."""

    observaciones = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ReabrirPeriodoInputSerializer(serializers.Serializer):
    """Payload de entrada para ``POST /api/contabilidad/periodos-contables/{id}/reabrir/``."""

    motivo = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class CerrarEjercicioInputSerializer(serializers.Serializer):
    """Payload de entrada para ``POST /api/contabilidad/periodos-contables/cerrar-ejercicio/``."""

    id_empresa = serializers.UUIDField()
    anio = serializers.IntegerField(min_value=1900, max_value=2100)
    cuenta_resultado_acumulado = serializers.UUIDField()
    fecha_cierre = serializers.DateField(required=False, allow_null=True)


class CerrarEjercicioResponseSerializer(serializers.Serializer):
    """Respuesta OpenAPI de ``POST /api/contabilidad/periodos-contables/cerrar-ejercicio/``."""

    anio = serializers.IntegerField(read_only=True)
    asiento_cierre = AsientoContableSerializer(read_only=True, allow_null=True)
    resultado_ejercicio = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    cantidad_cuentas_saldadas = serializers.IntegerField(read_only=True)
    periodos_cerrados = PeriodoContableSerializer(many=True, read_only=True)
