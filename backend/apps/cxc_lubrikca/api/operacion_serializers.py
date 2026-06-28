"""Serializers de los modelos de operación CxC Lubrikca (Fase 3).

``empresa`` nunca es writable (se inyecta en ``perform_create``). Los campos
congelados de ``Vinculacion`` (tasas, equivalentes) son de solo lectura: se
estampan en el servicio de captura, no por la API.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.cxc_lubrikca.models import (
    BandejaFacturacion,
    LineaPedidoLubrikca,
    PagoLubrikca,
    PedidoLubrikca,
    PrecioListaLubrikca,
    Vinculacion,
)

_READ_ONLY = ("id", "created_at", "updated_at")


class LineaPedidoLubrikcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = LineaPedidoLubrikca
        fields = (
            "id",
            "pedido",
            "linea_id",
            "producto",
            "marca",
            "categoria",
            "cantidad",
            "precio_unitario",
            "cantidad_entregada",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY


class BandejaFacturacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BandejaFacturacion
        fields = (
            "id",
            "pedido",
            "lista_aplicada",
            "precio_base_calculado",
            "descuentos_detalle",
            "total_descuentos",
            "ncs_calculadas",
            "total_motor",
            "requiere_revision",
            "candidata_a_cierre",
            "estado",
            "aprobado_por",
            "calculado_en",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields  # solo lectura: la salida la produce el motor


class PedidoLubrikcaSerializer(serializers.ModelSerializer):
    lineas = LineaPedidoLubrikcaSerializer(many=True, read_only=True)
    bandeja = BandejaFacturacionSerializer(read_only=True)

    class Meta:
        model = PedidoLubrikca
        fields = (
            "id",
            "so_id",
            "cliente_externo_id",
            "cliente_nombre",
            "vendedor_email",
            "fecha",
            "fecha_entrega",
            "monto_total",
            "lista_precios",
            "es_primera_compra",
            "facturada",
            "factura_id",
            "monto_facturado",
            "estado_entrega",
            "entregada_completa",
            "tiene_devolucion",
            "lineas",
            "bandeja",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY


class PrecioListaLubrikcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrecioListaLubrikca
        fields = (
            "id",
            "producto",
            "lista",
            "precio",
            "created_at",
            "updated_at",
        )
        read_only_fields = _READ_ONLY


class PagoLubrikcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoLubrikca
        fields = (
            "id",
            "pago_id",
            "cliente_externo_id",
            "monto",
            "moneda",
            "metodo_pago",
            "fecha_pago",
            "vendedor_email",
            "vinculado",
            "created_at",
            "updated_at",
        )
        read_only_fields = (*_READ_ONLY, "vinculado")


class VinculacionSerializer(serializers.ModelSerializer):
    """Lectura de vinculaciones. Los campos congelados son read-only: la creación
    se hace por la acción ``registrar`` (servicio de captura), no por POST."""

    class Meta:
        model = Vinculacion
        fields = (
            "id",
            "pedido",
            "pago",
            "monto_aplicado",
            "hora_pago_confirmada",
            "tasa_bcv_aplicada",
            "tasa_binance_aplicada",
            "es_tasa_heredada",
            "moneda_abono",
            "tipo_tasa_abono",
            "equiv_usd_bcv",
            "equiv_usd_binance",
            "equiv_ves_bcv",
            "equiv_ves_binance",
            "estado",
            "confirmado_por",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RegistrarVinculacionSerializer(serializers.Serializer):
    """Cuerpo de la acción ``registrar``."""

    pedido = serializers.UUIDField()
    pago = serializers.UUIDField()
    monto_aplicado = serializers.DecimalField(max_digits=18, decimal_places=4)
    hora_pago_confirmada = serializers.DateTimeField()
    es_tasa_heredada = serializers.BooleanField(required=False, default=False)


class ConfirmarCierreSerializer(serializers.Serializer):
    """Cuerpo de la acción ``confirmar``."""

    aprobado = serializers.BooleanField()
    comentarios = serializers.CharField(required=False, allow_blank=True, default="")
