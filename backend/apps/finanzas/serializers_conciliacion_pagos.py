"""
Serializers REST y de contrato OpenAPI para conciliación N:M de pagos (Ola A3).
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import AsignacionPago


class AsignacionPagoSerializer(serializers.ModelSerializer):
    """Representación de solo lectura de una ``AsignacionPago`` (whitelist CTF-005)."""

    contacto_nombre = serializers.CharField(
        source="id_contacto.nombre_completo",
        read_only=True,
        allow_blank=True,
        default="",
    )
    pago_referencia = serializers.CharField(
        source="id_pago.referencia",
        read_only=True,
        allow_null=True,
        allow_blank=True,
        default="",
    )
    moneda_documento_codigo = serializers.CharField(
        source="id_moneda_documento.codigo_iso",
        read_only=True,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = AsignacionPago
        fields = [
            "id_asignacion",
            "id_empresa",
            "id_contacto",
            "contacto_nombre",
            "id_pago",
            "pago_referencia",
            "tipo_documento",
            "id_documento",
            "id_cxc",
            "id_cxp",
            "id_factura_venta",
            "id_factura_compra",
            "id_abono_cxc",
            "id_abono_cxp",
            "monto_asignado_pago",
            "monto_asignado_documento",
            "id_moneda_documento",
            "moneda_documento_codigo",
            "tasa_aplicada",
            "diferencia_cambiaria",
            "tipo_diferencia",
            "estado",
            "fecha_aplicacion",
            "fecha_reversion",
            "motivo_reversion",
            "id_asiento",
            "id_asiento_reversion",
            "id_usuario_registro",
            "referencia_externa",
            "activo",
            "fecha_creacion",
        ]
        # La creación y reversión pasan por serializers de entrada dedicados y servicios
        # atómicos; ninguna FK del modelo es escribible por CRUD libre.
        read_only_fields = fields


class LineaConciliacionInputSerializer(serializers.Serializer):
    """Línea individual dentro de un lote de conciliación N:M."""

    tipo_documento = serializers.ChoiceField(choices=AsignacionPago.TIPO_DOCUMENTO_CHOICES)
    id_documento = serializers.CharField(max_length=64)
    monto_asignado_pago = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0.0001"),
    )
    monto_asignado_documento = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        required=False,
        allow_null=True,
    )
    tasa_aplicada = serializers.DecimalField(
        max_digits=18,
        decimal_places=8,
        min_value=Decimal("0.00000001"),
        required=False,
        allow_null=True,
    )
    tasa_original = serializers.DecimalField(
        max_digits=18,
        decimal_places=8,
        min_value=Decimal("0.00000001"),
        required=False,
        allow_null=True,
    )
    tasa_liquidacion = serializers.DecimalField(
        max_digits=18,
        decimal_places=8,
        min_value=Decimal("0.00000001"),
        required=False,
        allow_null=True,
    )
    moneda_documento = serializers.CharField(
        max_length=36,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )
    referencia_externa = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
    )


class ConciliarDocumentosInputSerializer(serializers.Serializer):
    """Payload de entrada para ``POST /api/finanzas/pagos/{id}/conciliar-documentos/``."""

    asignaciones = LineaConciliacionInputSerializer(many=True, allow_empty=False)
    descripcion = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    generar_asiento = serializers.BooleanField(required=False, default=True)


class CrearAsignacionPagoInputSerializer(ConciliarDocumentosInputSerializer):
    """Payload de entrada para ``POST /api/finanzas/asignaciones-pago/``."""

    pago = serializers.UUIDField()


class RevertirAsignacionInputSerializer(serializers.Serializer):
    """Payload de entrada para ``POST /api/finanzas/asignaciones-pago/{id}/revertir/``."""

    motivo = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ConciliarDocumentosResponseSerializer(serializers.Serializer):
    """Respuesta OpenAPI de aplicación de un pago a 1..N documentos."""

    pago_id = serializers.UUIDField(read_only=True)
    saldo_disponible = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    asignaciones = AsignacionPagoSerializer(many=True, read_only=True)


class PropuestaDistribucionItemSerializer(serializers.Serializer):
    tipo_documento = serializers.CharField(read_only=True)
    id_documento = serializers.CharField(read_only=True)
    referencia = serializers.CharField(read_only=True, allow_blank=True, default="")
    fecha_emision = serializers.DateField(read_only=True)
    fecha_vencimiento = serializers.DateField(read_only=True)
    moneda_documento = serializers.UUIDField(read_only=True)
    moneda_documento_codigo = serializers.CharField(read_only=True)
    saldo_pendiente_documento = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    tasa_aplicada = serializers.DecimalField(max_digits=18, decimal_places=8, read_only=True)
    monto_asignado_pago = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    monto_asignado_documento = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)


class OmitidaSinTasaSerializer(serializers.Serializer):
    tipo_documento = serializers.CharField(read_only=True)
    id_documento = serializers.CharField(read_only=True)
    moneda_codigo = serializers.CharField(read_only=True)
    motivo = serializers.CharField(read_only=True)


class SugerirDistribucionResponseSerializer(serializers.Serializer):
    """Respuesta OpenAPI de ``GET /api/finanzas/pagos/{id}/sugerir-distribucion/``."""

    pago_id = serializers.UUIDField(read_only=True)
    saldo_disponible = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    propuestas = PropuestaDistribucionItemSerializer(many=True, read_only=True)
    total_a_aplicar = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    saldo_a_favor_resultante = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    omitidas_sin_tasa = OmitidaSinTasaSerializer(many=True, read_only=True)


class ContactoResumenConciliacionSerializer(serializers.Serializer):
    id_contacto = serializers.UUIDField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    rif = serializers.CharField(read_only=True, allow_blank=True, default="")
    es_cliente = serializers.BooleanField(read_only=True)
    es_proveedor = serializers.BooleanField(read_only=True)


class SaldoMonedaConciliacionSerializer(serializers.Serializer):
    moneda_id = serializers.UUIDField(read_only=True)
    codigo_iso = serializers.CharField(read_only=True)
    simbolo = serializers.CharField(read_only=True)
    INGRESO = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    EGRESO = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    cantidad_pagos = serializers.IntegerField(read_only=True)


class SaldoAFavorResumenSerializer(serializers.Serializer):
    total_por_moneda = serializers.DictField(child=SaldoMonedaConciliacionSerializer(), read_only=True)
    total_pagos_con_saldo = serializers.IntegerField(read_only=True)


class PagoDisponibleConciliacionSerializer(serializers.Serializer):
    id_pago = serializers.UUIDField(read_only=True)
    fecha_pago = serializers.DateTimeField(read_only=True)
    tipo_operacion = serializers.CharField(read_only=True)
    monto = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    saldo_disponible = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    moneda_codigo = serializers.CharField(read_only=True)
    referencia = serializers.CharField(read_only=True, allow_blank=True, default="")
    tasa = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)


class ObligacionAbiertaConciliacionSerializer(serializers.Serializer):
    tipo_documento = serializers.CharField(read_only=True)
    id_documento = serializers.CharField(read_only=True)
    numero_documento = serializers.CharField(read_only=True)
    fecha_emision = serializers.DateField(read_only=True)
    fecha_vencimiento = serializers.DateField(read_only=True)
    monto_total = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    saldo_pendiente = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    moneda_codigo = serializers.CharField(read_only=True)
    estado = serializers.CharField(read_only=True)


class EstadoConciliacionContactoResponseSerializer(serializers.Serializer):
    """Respuesta OpenAPI de ``GET /api/finanzas/contactos/{id_contacto}/estado-conciliacion/``."""

    contacto = ContactoResumenConciliacionSerializer(read_only=True)
    saldo_a_favor = SaldoAFavorResumenSerializer(read_only=True)
    pagos_disponibles = PagoDisponibleConciliacionSerializer(many=True, read_only=True)
    obligaciones_abiertas = ObligacionAbiertaConciliacionSerializer(many=True, read_only=True)
    asignaciones_activas = AsignacionPagoSerializer(many=True, read_only=True)
