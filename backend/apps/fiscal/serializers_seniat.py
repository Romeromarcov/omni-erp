"""Serializers con whitelist explícita (CTF-005) para SENIAT 360°, Imprenta Digital e IGTF/ITF."""

from decimal import Decimal

from rest_framework import serializers

from .models import (
    ComprobanteRetencionISLR,
    ComprobanteRetencionIVA,
    ConceptoRetencionISLR,
    DocumentoImprentaDigital,
)


class ConceptoRetencionISLRSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConceptoRetencionISLR
        # CTF-005: whitelist explícita (CWE-915).
        fields = [
            "id",
            "codigo",
            "nombre",
            "tipo_persona_fiscal",
            "base_imponible_pct",
            "porcentaje_retencion",
            "aplica_sustraendo",
            "factor_sustraendo_ut",
            "activo",
        ]
        read_only_fields = fields


class ComprobanteRetencionIVASerializer(serializers.ModelSerializer):
    contacto_nombre = serializers.CharField(source="contacto.nombre", read_only=True)
    contacto_rif = serializers.CharField(source="contacto.rif", read_only=True)

    class Meta:
        model = ComprobanteRetencionIVA
        # CTF-005: whitelist explícita (CWE-915).
        fields = [
            "id_comprobante",
            "id_empresa",
            "numero_comprobante",
            "tipo_operacion",
            "contacto",
            "contacto_nombre",
            "contacto_rif",
            "factura_compra",
            "factura_venta",
            "fecha_emision",
            "periodo_impositivo",
            "numero_documento",
            "numero_control",
            "numero_documento_afectado",
            "tipo_transaccion",
            "monto_total_documento",
            "monto_exento",
            "base_imponible",
            "alicuota_iva",
            "monto_iva",
            "porcentaje_retencion",
            "monto_retenido",
            "estado",
            "asiento_contable",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class EmitirRetencionIVAInputSerializer(serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False)
    contacto = serializers.UUIDField()
    fecha_emision = serializers.DateField(required=False)
    numero_documento = serializers.CharField(max_length=64)
    numero_control = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    numero_documento_afectado = serializers.CharField(max_length=64, required=False, allow_blank=True, default="0")
    tipo_operacion = serializers.ChoiceField(choices=["COMPRA", "VENTA"], required=False, default="COMPRA")
    tipo_transaccion = serializers.ChoiceField(choices=["01", "02", "03"], required=False, default="01")
    base_imponible = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0"))
    monto_exento = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0"), required=False, default=Decimal("0")
    )
    alicuota_iva = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        required=False,
        default=Decimal("16.00"),
    )
    monto_iva = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0"), required=False)
    monto_total_documento = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0"), required=False
    )
    porcentaje_retencion = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False
    )
    factura_compra = serializers.UUIDField(required=False, allow_null=True)
    factura_venta = serializers.UUIDField(required=False, allow_null=True)


class ComprobanteRetencionISLRSerializer(serializers.ModelSerializer):
    contacto_nombre = serializers.CharField(source="contacto.nombre", read_only=True)
    contacto_rif = serializers.CharField(source="contacto.rif", read_only=True)
    concepto_codigo = serializers.CharField(source="concepto.codigo", read_only=True)
    concepto_nombre = serializers.CharField(source="concepto.nombre", read_only=True)

    class Meta:
        model = ComprobanteRetencionISLR
        # CTF-005: whitelist explícita (CWE-915).
        fields = [
            "id_comprobante",
            "id_empresa",
            "numero_comprobante",
            "contacto",
            "contacto_nombre",
            "contacto_rif",
            "concepto",
            "concepto_codigo",
            "concepto_nombre",
            "factura_compra",
            "fecha_emision",
            "periodo_impositivo",
            "numero_factura",
            "numero_control",
            "monto_operacion",
            "valor_ut_aplicado",
            "sustraendo",
            "porcentaje_retencion",
            "monto_retenido",
            "estado",
            "asiento_contable",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class EmitirRetencionISLRInputSerializer(serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False)
    contacto = serializers.UUIDField()
    concepto = serializers.UUIDField()
    fecha_emision = serializers.DateField(required=False)
    numero_factura = serializers.CharField(max_length=64)
    numero_control = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    monto_operacion = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.01"))
    valor_ut = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0"), required=False)
    factura_compra = serializers.UUIDField(required=False, allow_null=True)
    omitir_exencion = serializers.BooleanField(required=False, default=False)


class DocumentoImprentaDigitalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoImprentaDigital
        # CTF-005: whitelist explícita (CWE-915).
        fields = [
            "id_emision",
            "id_empresa",
            "proveedor",
            "tipo_documento",
            "referencia_documento",
            "numero_control_asignado",
            "codigo_validacion",
            "url_verificacion",
            "estado",
            "emitido_en",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields


class EmitirImprentaDigitalInputSerializer(serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False)
    tipo_documento = serializers.ChoiceField(choices=["FACTURA", "NOTA_CREDITO", "NOTA_DEBITO", "GUIA_DESPACHO"])
    referencia_documento = serializers.CharField(max_length=64)
    proveedor = serializers.ChoiceField(choices=["SIMULADO", "UNIDIGITAL"], required=False)
    payload = serializers.DictField(required=False, default=dict)


class CalcularIGTFITFInputSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0"))
    moneda_iso = serializers.CharField(max_length=8)
    es_contribuyente_especial = serializers.BooleanField(required=False, default=False)
    es_debito_bancario = serializers.BooleanField(required=False, default=False)
    alicuota_igtf = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("3.00")
    )
    alicuota_itf = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("2.00")
    )
