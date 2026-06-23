from rest_framework import serializers

from .models import (
    CategoriaProducto,
    ConversionUnidadMedida,
    MovimientoInventario,
    OperacionInventario,
    OperacionInventarioLinea,
    OperacionInventarioPaso,
    PasoOperacion,
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


class PasoOperacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PasoOperacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_paso_operacion",
            "id_empresa",
            "id_almacen",
            "tipo_operacion",
            "nombre_paso",
            "secuencia",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]


class OperacionInventarioPasoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperacionInventarioPaso
        fields = [
            "id_operacion_paso",
            "secuencia",
            "nombre_paso",
            "confirmado",
            "id_usuario_confirmacion",
            "fecha_confirmacion",
        ]
        read_only_fields = fields


class OperacionInventarioLineaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)

    class Meta:
        model = OperacionInventarioLinea
        fields = [
            "id_linea",
            "id_producto",
            "producto_nombre",
            "id_variante",
            "cantidad",
            "costo_unitario",
        ]


class OperacionInventarioSerializer(serializers.ModelSerializer):
    """Lectura: operación con sus pasos y líneas anidados."""

    pasos = OperacionInventarioPasoSerializer(many=True, read_only=True)
    lineas = OperacionInventarioLineaSerializer(many=True, read_only=True)

    class Meta:
        model = OperacionInventario
        fields = [
            "id_operacion",
            "numero",
            "tipo_operacion",
            "origen_tipo",
            "origen_id",
            "id_almacen",
            "id_almacen_contraparte",
            "estado",
            "motivo",
            "fecha",
            "id_empresa",
            "pasos",
            "lineas",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["numero", "estado", "id_empresa", "pasos", "lineas"]


class _LineaInputSerializer(serializers.Serializer):
    producto = serializers.UUIDField()
    variante = serializers.UUIDField(required=False, allow_null=True)
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4)
    costo_unitario = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True
    )


class CrearOperacionSerializer(serializers.Serializer):
    """Escritura: crea una operación con su lista de líneas."""

    almacen = serializers.UUIDField()
    origen_tipo = serializers.ChoiceField(choices=[c[0] for c in OperacionInventario.ORIGENES])
    origen_id = serializers.UUIDField(required=False, allow_null=True)
    almacen_contraparte = serializers.UUIDField(required=False, allow_null=True)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    lineas = _LineaInputSerializer(many=True)
