from rest_framework import serializers

from .models import (
    DetalleFacturaCompra,
    DetalleOfertaProveedor,
    DetalleOrdenCompra,
    DetalleRecepcionMercancia,
    DetalleRequisicionCompra,
    DetalleSolicitudCotizacion,
    FacturaCompra,
    OfertaProveedor,
    OrdenCompra,
    RecepcionMercancia,
    RequisicionCompra,
    SolicitudCotizacion,
)


class OrdenCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenCompra
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_orden_compra", "fecha_creacion")


class DetalleOrdenCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleOrdenCompra
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_orden_compra",
            "id_orden_compra",
            "id_producto",
            "cantidad",
            "precio_unitario",
            "subtotal",
            "observaciones",
        ]


class RecepcionMercanciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecepcionMercancia
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_recepcion", "fecha_creacion")


class FacturaCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacturaCompra
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_factura_compra", "fecha_creacion")


class RequisicionCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisicionCompra
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_requisicion",
            "id_solicitante",
            "id_departamento",
            "numero_requisicion",
            "fecha_requisicion",
            "estado",
            "prioridad",
            "fecha_necesidad",
            "justificacion",
            "observaciones",
            "fecha_creacion",
            "id_empresa",
        ]
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_requisicion", "fecha_creacion")


class DetalleRequisicionCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleRequisicionCompra
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_requisicion",
            "id_requisicion",
            "id_producto",
            "cantidad_solicitada",
            "precio_estimado",
            "justificacion",
            "observaciones",
        ]


class SolicitudCotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitudCotizacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_solicitud_cotizacion",
            "numero_solicitud",
            "fecha_solicitud",
            "fecha_vencimiento",
            "estado",
            "observaciones",
            "fecha_creacion",
            "id_empresa",
        ]
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_solicitud_cotizacion", "fecha_creacion")


class DetalleSolicitudCotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleSolicitudCotizacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_solicitud",
            "id_solicitud_cotizacion",
            "id_producto",
            "cantidad",
            "especificaciones",
            "observaciones",
        ]


class OfertaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfertaProveedor
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_oferta",
            "id_solicitud_cotizacion",
            "id_proveedor",
            "numero_oferta",
            "fecha_oferta",
            "fecha_vencimiento",
            "estado",
            "monto_total",
            "condiciones_pago",
            "tiempo_entrega",
            "observaciones",
            "fecha_creacion",
        ]


class DetalleOfertaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleOfertaProveedor
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_oferta",
            "id_oferta",
            "id_producto",
            "cantidad",
            "precio_unitario",
            "subtotal",
            "tiempo_entrega",
            "observaciones",
        ]


class DetalleRecepcionMercanciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleRecepcionMercancia
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_recepcion",
            "id_recepcion",
            "id_producto",
            "cantidad_esperada",
            "cantidad_recibida",
            "costo_unitario",
            "subtotal",
            "estado_mercancia",
            "observaciones",
        ]


class DetalleFacturaCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleFacturaCompra
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_factura",
            "id_factura_compra",
            "id_producto",
            "cantidad",
            "precio_unitario",
            "descuento_porcentaje",
            "descuento_monto",
            "subtotal",
            "monto_impuesto",
            "total_linea",
            "observaciones",
        ]
