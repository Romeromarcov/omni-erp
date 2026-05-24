from rest_framework import serializers

from .models import (
    CategoriaProducto,
    ConversionUnidadMedida,
    MovimientoInventario,
    Producto,
    StockActual,
    StockConsignacionCliente,
    StockConsignacionProveedor,
    UnidadMedida,
    VarianteProducto,
)


class UnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadMedida
        fields = "__all__"


class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = "__all__"


class ProductoSerializer(serializers.ModelSerializer):
    nombre_categoria = serializers.CharField(source="id_categoria.nombre_categoria", read_only=True)
    nombre_unidad_medida = serializers.CharField(
        source="id_unidad_medida_base.nombre", read_only=True
    )

    class Meta:
        model = Producto
        fields = "__all__"
        read_only_fields = ["fecha_creacion", "fecha_actualizacion"]


class VarianteProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarianteProducto
        fields = "__all__"


class StockActualSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)
    almacen_nombre = serializers.CharField(source="id_almacen.nombre_almacen", read_only=True)

    class Meta:
        model = StockActual
        fields = "__all__"
        read_only_fields = ["fecha_ultima_actualizacion"]


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)
    almacen_origen_nombre = serializers.CharField(
        source="id_almacen_origen.nombre_almacen", read_only=True, allow_null=True
    )
    almacen_destino_nombre = serializers.CharField(
        source="id_almacen_destino.nombre_almacen", read_only=True, allow_null=True
    )

    class Meta:
        model = MovimientoInventario
        fields = "__all__"
        # id_usuario_registro is injected by perform_create from request.user
        read_only_fields = ["id_usuario_registro", "fecha_creacion", "fecha_actualizacion"]


class ConversionUnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversionUnidadMedida
        fields = "__all__"


class StockConsignacionClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockConsignacionCliente
        fields = "__all__"


class StockConsignacionProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockConsignacionProveedor
        fields = "__all__"
