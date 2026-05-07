from rest_framework import serializers
from .models import (
    OrdenCompra, DetalleOrdenCompra, RecepcionMercancia, FacturaCompra,
    RequisicionCompra, DetalleRequisicionCompra, SolicitudCotizacion,
    DetalleSolicitudCotizacion, OfertaProveedor, DetalleOfertaProveedor,
    DetalleRecepcionMercancia, DetalleFacturaCompra
)

class OrdenCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenCompra
        fields = '__all__'

class DetalleOrdenCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleOrdenCompra
        fields = '__all__'

class RecepcionMercanciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecepcionMercancia
        fields = '__all__'

class FacturaCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacturaCompra
        fields = '__all__'


class RequisicionCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisicionCompra
        fields = '__all__'


class DetalleRequisicionCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleRequisicionCompra
        fields = '__all__'


class SolicitudCotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitudCotizacion
        fields = '__all__'


class DetalleSolicitudCotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleSolicitudCotizacion
        fields = '__all__'


class OfertaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfertaProveedor
        fields = '__all__'


class DetalleOfertaProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleOfertaProveedor
        fields = '__all__'


class DetalleRecepcionMercanciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleRecepcionMercancia
        fields = '__all__'


class DetalleFacturaCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleFacturaCompra
        fields = '__all__'
