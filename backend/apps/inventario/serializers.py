from rest_framework import serializers
from .models import (
    UnidadMedida, CategoriaProducto, Producto, VarianteProducto,
    StockActual, MovimientoInventario, ConversionUnidadMedida,
    StockConsignacionCliente, StockConsignacionProveedor
)

class UnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadMedida
        fields = '__all__'

class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = '__all__'

class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = '__all__'


class VarianteProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarianteProducto
        fields = '__all__'


class StockActualSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockActual
        fields = '__all__'


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInventario
        fields = '__all__'


class ConversionUnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversionUnidadMedida
        fields = '__all__'


class StockConsignacionClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockConsignacionCliente
        fields = '__all__'


class StockConsignacionProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockConsignacionProveedor
        fields = '__all__'
