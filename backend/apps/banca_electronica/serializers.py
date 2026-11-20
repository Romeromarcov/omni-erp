from rest_framework import serializers

from apps.core.models import Empresa
from apps.core.serializer_mixins import (
    empresa_efectiva_contexto,
    empresas_visibles_contexto,
    validar_fk_empresa,
)
from apps.finanzas.models import CuentaBancariaEmpresa, Pago
from apps.nomina.models import Nomina, ProcesoNomina

from .models import DetalleLotePagoBancario, LotePagoBancario


class DetalleLotePagoBancarioSerializer(serializers.ModelSerializer):
    """Línea de detalle de un lote de pago bancario (solo lectura)."""

    class Meta:
        model = DetalleLotePagoBancario
        fields = [
            "id_detalle",
            "id_lote_pago",
            "id_pago",
            "id_nomina",
            "beneficiario_nombre",
            "beneficiario_identificacion",
            "cuenta_destino",
            "banco_destino",
            "monto",
            "referencia_linea",
            "concepto",
        ]
        read_only_fields = fields


class LotePagoBancarioSerializer(serializers.ModelSerializer):
    """Lote de pagos masivos VE consolidado sobre ``finanzas.CuentaBancariaEmpresa``."""

    detalles = DetalleLotePagoBancarioSerializer(many=True, read_only=True)
    empresa_nombre = serializers.SerializerMethodField()
    cuenta_bancaria_nombre = serializers.CharField(source="id_cuenta_bancaria.nombre_banco", read_only=True)
    cuenta_bancaria_numero = serializers.CharField(source="id_cuenta_bancaria.numero_cuenta", read_only=True)

    class Meta:
        model = LotePagoBancario
        fields = [
            "id_lote_pago",
            "id_empresa",
            "empresa_nombre",
            "id_cuenta_bancaria",
            "cuenta_bancaria_nombre",
            "cuenta_bancaria_numero",
            "tipo_lote",
            "formato_banco",
            "referencia_lote",
            "fecha_valor",
            "estado",
            "id_proceso_nomina",
            "total_registros",
            "monto_total",
            "sha256_archivo",
            "nombre_archivo",
            "generado_por",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
            "detalles",
        ]
        # Creación/transición mediante endpoints de servicio dedicados.
        read_only_fields = fields

    def get_empresa_nombre(self, obj: LotePagoBancario) -> str:
        return obj.id_empresa.nombre_comercial or obj.id_empresa.nombre_legal


def _resolver_empresa_y_cuenta(
    serializer: serializers.Serializer,
    id_empresa_val,
    id_cuenta_val,
) -> tuple[Empresa, CuentaBancariaEmpresa, str, set[str] | None]:
    visibles = empresas_visibles_contexto(serializer)
    cuenta = CuentaBancariaEmpresa.objects.select_related("id_empresa").filter(pk=id_cuenta_val).first()
    if cuenta is None:
        raise serializers.ValidationError({"id_cuenta_bancaria": "La cuenta bancaria no existe."})

    if id_empresa_val is not None:
        emp = Empresa.objects.filter(pk=id_empresa_val, activo=True).first()
        if emp is None or (visibles is not None and str(emp.pk) not in visibles):
            raise serializers.ValidationError({"id_empresa": "No tiene acceso a la empresa especificada."})
        empresa_ref = str(emp.pk)
        validar_fk_empresa(cuenta, "id_cuenta_bancaria", empresa_ref, visibles, etiqueta="la cuenta bancaria")
        return emp, cuenta, empresa_ref, visibles

    if visibles is not None and str(cuenta.id_empresa_id) not in visibles:
        validar_fk_empresa(
            cuenta,
            "id_cuenta_bancaria",
            empresa_efectiva_contexto(serializer),
            visibles,
            etiqueta="la cuenta bancaria",
        )
    emp = cuenta.id_empresa
    empresa_ref = str(emp.pk)
    validar_fk_empresa(cuenta, "id_cuenta_bancaria", empresa_ref, visibles, etiqueta="la cuenta bancaria")
    return emp, cuenta, empresa_ref, visibles


class GenerarLoteProveedoresInputSerializer(serializers.Serializer):
    """Entrada para generación atómica de lotes de pago a proveedores."""

    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    id_cuenta_bancaria = serializers.UUIDField()
    pagos_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    formato_banco = serializers.ChoiceField(choices=LotePagoBancario.FORMATOS_BANCO)
    fecha_valor = serializers.DateField()
    referencia_lote = serializers.CharField(max_length=60, required=False, allow_blank=True, allow_null=True)
    cuentas_destino_override = serializers.DictField(
        child=serializers.CharField(max_length=50),
        required=False,
    )

    def validate(self, attrs: dict) -> dict:
        emp, cuenta, empresa_ref, visibles = _resolver_empresa_y_cuenta(
            self,
            attrs.get("id_empresa"),
            attrs["id_cuenta_bancaria"],
        )

        pagos_ids = [str(pid) for pid in attrs["pagos_ids"]]
        pagos_db = Pago.objects.filter(pk__in=pagos_ids)
        pagos_map = {str(p.pk): p for p in pagos_db}

        for pid in pagos_ids:
            pago = pagos_map.get(pid)
            if pago is None:
                raise serializers.ValidationError({"pagos_ids": f"El pago {pid} no existe."})
            validar_fk_empresa(pago, "pagos_ids", empresa_ref, visibles, etiqueta=f"el pago {pid}")

        overrides = attrs.get("cuentas_destino_override") or {}
        pagos_set = set(pagos_ids)
        for key in overrides:
            if str(key) not in pagos_set:
                raise serializers.ValidationError(
                    {"cuentas_destino_override": f"El pago {key} no pertenece al lote solicitado."}
                )

        attrs["empresa"] = emp
        attrs["cuenta_bancaria"] = cuenta
        return attrs


class GenerarLoteNominaInputSerializer(serializers.Serializer):
    """Entrada para generación atómica de lotes bancarios de nómina."""

    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    id_cuenta_bancaria = serializers.UUIDField()
    id_proceso_nomina = serializers.UUIDField()
    formato_banco = serializers.ChoiceField(choices=LotePagoBancario.FORMATOS_BANCO)
    fecha_valor = serializers.DateField()
    referencia_lote = serializers.CharField(max_length=60, required=False, allow_blank=True, allow_null=True)
    cuentas_empleados = serializers.DictField(
        child=serializers.CharField(max_length=50),
        required=False,
    )

    def validate(self, attrs: dict) -> dict:
        emp, cuenta, empresa_ref, visibles = _resolver_empresa_y_cuenta(
            self,
            attrs.get("id_empresa"),
            attrs["id_cuenta_bancaria"],
        )

        proceso = ProcesoNomina.objects.filter(pk=attrs["id_proceso_nomina"]).first()
        if proceso is None:
            raise serializers.ValidationError({"id_proceso_nomina": "El proceso de nómina no existe."})
        validar_fk_empresa(
            proceso,
            "id_proceso_nomina",
            empresa_ref,
            visibles,
            etiqueta="el proceso de nómina",
        )

        cuentas_empleados = attrs.get("cuentas_empleados") or {}
        if cuentas_empleados:
            validos: set[str] = set()
            for nid, eid in Nomina.objects.filter(id_proceso_nomina=proceso).values_list("pk", "id_empleado_id"):
                validos.add(str(nid))
                validos.add(str(eid))
            for key in cuentas_empleados:
                if str(key) not in validos:
                    raise serializers.ValidationError(
                        {"cuentas_empleados": f"El identificador '{key}' no pertenece a este proceso de nómina."}
                    )

        attrs["empresa"] = emp
        attrs["cuenta_bancaria"] = cuenta
        attrs["proceso_nomina"] = proceso
        return attrs


class ValidarReferenciaInputSerializer(serializers.Serializer):
    """Entrada para detección de referencias bancarias duplicadas dentro del tenant."""

    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    id_cuenta_bancaria = serializers.UUIDField(required=False, allow_null=True)
    referencia = serializers.CharField(max_length=100, allow_blank=True, trim_whitespace=False)
    excluir_pago_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        visibles = empresas_visibles_contexto(self)
        cuenta = None
        if attrs.get("id_cuenta_bancaria") is not None:
            cuenta = (
                CuentaBancariaEmpresa.objects.select_related("id_empresa")
                .filter(pk=attrs["id_cuenta_bancaria"])
                .first()
            )
            if cuenta is None:
                raise serializers.ValidationError({"id_cuenta_bancaria": "La cuenta bancaria no existe."})

        if attrs.get("id_empresa") is not None:
            emp = Empresa.objects.filter(pk=attrs["id_empresa"], activo=True).first()
            if emp is None or (visibles is not None and str(emp.pk) not in visibles):
                raise serializers.ValidationError({"id_empresa": "No tiene acceso a la empresa especificada."})
            if cuenta is not None:
                validar_fk_empresa(
                    cuenta,
                    "id_cuenta_bancaria",
                    str(emp.pk),
                    visibles,
                    etiqueta="la cuenta bancaria",
                )
        elif cuenta is not None:
            if visibles is not None and str(cuenta.id_empresa_id) not in visibles:
                validar_fk_empresa(
                    cuenta,
                    "id_cuenta_bancaria",
                    empresa_efectiva_contexto(self),
                    visibles,
                    etiqueta="la cuenta bancaria",
                )
            emp = cuenta.id_empresa
            validar_fk_empresa(
                cuenta,
                "id_cuenta_bancaria",
                str(emp.pk),
                visibles,
                etiqueta="la cuenta bancaria",
            )
        else:
            empresa_ref = empresa_efectiva_contexto(self)
            emp = Empresa.objects.filter(pk=empresa_ref, activo=True).first() if empresa_ref else None
            if emp is None or (visibles is not None and str(emp.pk) not in visibles):
                raise serializers.ValidationError({"id_empresa": "No se pudo determinar la empresa."})

        if attrs.get("excluir_pago_id") is not None:
            pago = Pago.objects.filter(pk=attrs["excluir_pago_id"]).first()
            if pago is not None:
                validar_fk_empresa(
                    pago,
                    "excluir_pago_id",
                    str(emp.pk),
                    visibles,
                    etiqueta="el pago excluido",
                )

        attrs["empresa"] = emp
        attrs["cuenta_bancaria"] = cuenta
        return attrs


class CoincidenciaReferenciaSerializer(serializers.Serializer):
    origen = serializers.CharField()
    id = serializers.CharField()
    detalle = serializers.CharField()


class ValidarReferenciaResponseSerializer(serializers.Serializer):
    duplicada = serializers.BooleanField()
    referencia_normalizada = serializers.CharField()
    coincidencias = CoincidenciaReferenciaSerializer(many=True)


class ValidarCuentaVeInputSerializer(serializers.Serializer):
    numero_cuenta = serializers.CharField(max_length=60, allow_blank=True)


class ValidarCuentaVeResponseSerializer(serializers.Serializer):
    valida = serializers.BooleanField()
    numero_normalizado = serializers.CharField()
    codigo_banco = serializers.CharField(allow_null=True)
    banco_nombre = serializers.CharField(allow_null=True)
    errores = serializers.ListField(child=serializers.CharField())
