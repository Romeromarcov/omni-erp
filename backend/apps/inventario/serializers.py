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
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_unidad_medida",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "referencia_externa",
            "documento_json",
            "nombre",
            "abreviatura",
            "tipo",
            "id_empresa",
        ]


class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_categoria_producto",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "referencia_externa",
            "documento_json",
            "nombre_categoria",
            "descripcion",
            "id_empresa",
            "id_categoria_padre",
        ]


class ProductoSerializer(serializers.ModelSerializer):
    nombre_categoria = serializers.CharField(source="id_categoria.nombre_categoria", read_only=True)
    nombre_unidad_medida = serializers.CharField(
        source="id_unidad_medida_base.nombre", read_only=True
    )

    class Meta:
        model = Producto
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_producto",
            "nombre_categoria",
            "nombre_unidad_medida",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "referencia_externa",
            "documento_json",
            "tipo_operacion",
            "fecha_cierre_estimada",
            "nombre_producto",
            "sku",
            "descripcion",
            "tipo_producto",
            "maneja_lotes",
            "maneja_seriales",
            "costo_promedio",
            "precio_venta_sugerido",
            "punto_reorden",
            "id_empresa",
            "id_categoria",
            "id_unidad_medida_base",
            "id_moneda_precio",
            "id_configuracion_impuesto_venta_default",
            "id_configuracion_impuesto_compra_default",
        ]
        read_only_fields = ["fecha_creacion", "fecha_actualizacion"]


class VarianteProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarianteProducto
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_variante",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "codigo_variante",
            "atributos_json",
            "sku",
            "id_producto",
        ]


class StockActualSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)
    almacen_nombre = serializers.CharField(source="id_almacen.nombre_almacen", read_only=True)

    class Meta:
        model = StockActual
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_stock_actual",
            "producto_nombre",
            "almacen_nombre",
            "cantidad_disponible",
            "cantidad_comprometida",
            "cantidad_en_transito",
            "cantidad_minima",
            "cantidad_maxima",
            "fecha_ultima_actualizacion",
            "id_empresa",
            "id_producto",
            "id_variante",
            "id_almacen",
        ]
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
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_movimiento_inventario",
            "producto_nombre",
            "almacen_origen_nombre",
            "almacen_destino_nombre",
            "fecha_creacion",
            "fecha_actualizacion",
            "fecha_hora_movimiento",
            "tipo_movimiento",
            "cantidad",
            "costo_unitario_movimiento",
            "id_documento_origen",
            "nombre_modelo_origen",
            "observaciones",
            "id_empresa",
            "id_producto",
            "id_variante",
            "id_almacen_origen",
            "id_almacen_destino",
            "id_usuario_registro",
        ]
        # id_usuario_registro is injected by perform_create from request.user
        read_only_fields = ["id_usuario_registro", "fecha_creacion", "fecha_actualizacion"]


class ConversionUnidadMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversionUnidadMedida
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_conversion",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "factor_conversion",
            "id_empresa",
            "id_producto",
            "id_unidad_origen",
            "id_unidad_destino",
        ]


class StockConsignacionClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockConsignacionCliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_stock_consignacion",
            "fecha_creacion",
            "fecha_actualizacion",
            "cantidad_consignada",
            "cantidad_vendida",
            "cantidad_devuelta",
            "fecha_consignacion",
            "fecha_vencimiento",
            "precio_unitario_consignacion",
            "estado",
            "id_empresa",
            "id_cliente",
            "id_producto",
            "id_variante",
            "id_moneda",
        ]


class StockConsignacionProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockConsignacionProveedor
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_stock_consignacion",
            "fecha_creacion",
            "fecha_actualizacion",
            "cantidad_recibida",
            "cantidad_consumida",
            "cantidad_devuelta",
            "fecha_recepcion",
            "fecha_vencimiento",
            "costo_unitario_consignacion",
            "estado",
            "id_empresa",
            "id_proveedor",
            "id_producto",
            "id_variante",
            "id_moneda",
        ]
