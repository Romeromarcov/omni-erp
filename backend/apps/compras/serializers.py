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
        fields = "__all__"
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_orden_compra", "fecha_creacion")


class DetalleOrdenCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleOrdenCompra
        fields = "__all__"


class RecepcionMercanciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecepcionMercancia
        fields = "__all__"
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_recepcion", "fecha_creacion")


class FacturaCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacturaCompra
        fields = "__all__"
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_factura_compra", "fecha_creacion")


class RequisicionCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisicionCompra
        fields = "__all__"
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_requisicion", "fecha_creacion")


class DetalleRequisicionCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleRequisicionCompra
        fields = "__all__"


class SolicitudCotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitudCotizacion
        fields = "__all__"
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_solicitud_cotizacion", "fecha_creacion")


class DetalleSolicitudCotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleSolicitudCotizacion
        fields = "__all__"


class OfertaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfertaProveedor
        fields = "__all__"


class DetalleOfertaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleOfertaProveedor
        fields = "__all__"


class DetalleRecepcionMercanciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleRecepcionMercancia
        fields = "__all__"


class DetalleFacturaCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleFacturaCompra
        fields = "__all__"
