from decimal import Decimal

from rest_framework import serializers

from apps.core.serializer_mixins import (
    empresa_efectiva_contexto,
    empresas_visibles_contexto,
    validar_fk_empresa,
)

from .models import (
    CategoriaProducto,
    ConversionUnidadMedida,
    LoteProducto,
    MovimientoInventario,
    OperacionInventario,
    OperacionInventarioLinea,
    OperacionInventarioPaso,
    PasoOperacion,
    Producto,
    ReglaReabastecimiento,
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
    nombre_unidad_medida = serializers.CharField(source="id_unidad_medida_base.nombre", read_only=True)

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
            "estrategia_salida",
            "es_vendible",
            "es_comprable",
            "costo_promedio",
            "metodo_valoracion",
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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        visibles = empresas_visibles_contexto(self)
        if self.instance is not None and "id_empresa" in attrs:
            nueva_emp = attrs["id_empresa"]
            if nueva_emp is None or nueva_emp.pk != self.instance.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_empresa": "No se puede cambiar la empresa de un producto existente."}
                )

        emp = attrs["id_empresa"] if "id_empresa" in attrs else getattr(self.instance, "id_empresa", None)
        empresa_ref = str(emp.pk) if emp is not None else empresa_efectiva_contexto(self)
        if emp is not None and visibles is not None and str(emp.pk) not in visibles:
            raise serializers.ValidationError({"id_empresa": "Empresa fuera de su alcance."})

        categoria = attrs["id_categoria"] if "id_categoria" in attrs else getattr(self.instance, "id_categoria", None)
        unidad = (
            attrs["id_unidad_medida_base"]
            if "id_unidad_medida_base" in attrs
            else getattr(self.instance, "id_unidad_medida_base", None)
        )
        validar_fk_empresa(categoria, "id_categoria", empresa_ref, visibles, etiqueta="Categoría")
        validar_fk_empresa(unidad, "id_unidad_medida_base", empresa_ref, visibles, etiqueta="Unidad de medida base")

        moneda = (
            attrs["id_moneda_precio"]
            if "id_moneda_precio" in attrs
            else getattr(self.instance, "id_moneda_precio", None)
        )
        if (
            moneda is not None
            and not getattr(moneda, "es_generica", False)
            and not getattr(moneda, "es_publica", False)
            and getattr(moneda, "empresa_id", None) is not None
        ):
            validar_fk_empresa(
                moneda,
                "id_moneda_precio",
                empresa_ref,
                visibles,
                etiqueta="Moneda",
                empresa_attr="empresa_id",
            )

        for campo, etiqueta in (
            ("id_configuracion_impuesto_venta_default", "Configuración de impuesto de venta"),
            ("id_configuracion_impuesto_compra_default", "Configuración de impuesto de compra"),
        ):
            imp = attrs[campo] if campo in attrs else getattr(self.instance, campo, None)
            if (
                imp is not None
                and not getattr(imp, "es_generica", False)
                and getattr(imp, "empresa_id", None) is not None
            ):
                validar_fk_empresa(imp, campo, empresa_ref, visibles, etiqueta=etiqueta, empresa_attr="empresa_id")
        return attrs


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
    id_lote = serializers.PrimaryKeyRelatedField(queryset=LoteProducto.objects.all(), required=False, allow_null=True)
    lote_numero = serializers.CharField(source="id_lote.numero_lote", read_only=True, allow_null=True)
    numero_lote = serializers.CharField(required=False, allow_blank=True, max_length=80, write_only=True)
    fecha_fabricacion = serializers.DateField(required=False, allow_null=True, write_only=True)
    fecha_vencimiento = serializers.DateField(required=False, allow_null=True, write_only=True)

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
            "id_lote",
            "lote_numero",
            "numero_lote",
            "fecha_fabricacion",
            "fecha_vencimiento",
            "id_usuario_registro",
        ]
        # id_usuario_registro is injected by perform_create from request.user
        read_only_fields = ["id_usuario_registro", "fecha_creacion", "fecha_actualizacion"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        emp = attrs["id_empresa"] if "id_empresa" in attrs else getattr(self.instance, "id_empresa", None)
        empresa_ref = str(emp.pk) if emp is not None else empresa_efectiva_contexto(self)
        visibles = empresas_visibles_contexto(self)
        if emp is not None and visibles is not None and str(emp.pk) not in visibles:
            raise serializers.ValidationError({"id_empresa": "Empresa fuera de su alcance."})

        producto = attrs["id_producto"] if "id_producto" in attrs else getattr(self.instance, "id_producto", None)
        variante = attrs["id_variante"] if "id_variante" in attrs else getattr(self.instance, "id_variante", None)
        alm_orig = (
            attrs["id_almacen_origen"]
            if "id_almacen_origen" in attrs
            else getattr(self.instance, "id_almacen_origen", None)
        )
        alm_dest = (
            attrs["id_almacen_destino"]
            if "id_almacen_destino" in attrs
            else getattr(self.instance, "id_almacen_destino", None)
        )
        lote = attrs["id_lote"] if "id_lote" in attrs else getattr(self.instance, "id_lote", None)

        validar_fk_empresa(producto, "id_producto", empresa_ref, visibles, etiqueta="Producto")
        validar_fk_empresa(alm_orig, "id_almacen_origen", empresa_ref, visibles, etiqueta="Almacén origen")
        validar_fk_empresa(alm_dest, "id_almacen_destino", empresa_ref, visibles, etiqueta="Almacén destino")
        if variante is not None:
            validar_fk_empresa(variante.id_producto, "id_variante", empresa_ref, visibles, etiqueta="Variante")
            if producto is not None and variante.id_producto_id != producto.pk:
                raise serializers.ValidationError({"id_variante": "La variante no pertenece al producto indicado."})
        if lote is not None:
            validar_fk_empresa(lote, "id_lote", empresa_ref, visibles, etiqueta="Lote")
            if producto is not None and lote.id_producto_id != producto.pk:
                raise serializers.ValidationError({"id_lote": "El lote no pertenece al producto indicado."})
            var_id = variante.pk if variante is not None else None
            if lote.id_variante_id != var_id:
                raise serializers.ValidationError({"id_lote": "El lote no coincide con la variante indicada."})
            num_lote = (attrs.get("numero_lote") or "").strip()
            if num_lote and lote.numero_lote != num_lote:
                raise serializers.ValidationError(
                    {"numero_lote": "El numero_lote no coincide con el id_lote seleccionado."}
                )
        fecha_fab = attrs.get("fecha_fabricacion")
        fecha_ven = attrs.get("fecha_vencimiento")
        if fecha_fab is not None and fecha_ven is not None and fecha_ven < fecha_fab:
            raise serializers.ValidationError(
                {"fecha_vencimiento": "La fecha de vencimiento no puede ser anterior a la de fabricación."}
            )
        return attrs


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
        # Serializer SOLO de lectura: la creación va por CrearOperacionSerializer,
        # que acota cada FK a la empresa visible del usuario. Marcar todo read-only
        # evita exponer FKs writable sin scope (SEC-M1 / TenantFKScopeMixin).
        read_only_fields = [
            "numero",
            "estado",
            "id_empresa",
            "pasos",
            "lineas",
            "tipo_operacion",
            "origen_tipo",
            "origen_id",
            "id_almacen",
            "id_almacen_contraparte",
            "motivo",
            "fecha",
        ]


class _LineaInputSerializer(serializers.Serializer):
    producto = serializers.UUIDField()
    variante = serializers.UUIDField(required=False, allow_null=True)
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4)
    costo_unitario = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)


class CrearOperacionSerializer(serializers.Serializer):
    """Escritura: crea una operación con su lista de líneas."""

    almacen = serializers.UUIDField()
    origen_tipo = serializers.ChoiceField(choices=[c[0] for c in OperacionInventario.ORIGENES])
    origen_id = serializers.UUIDField(required=False, allow_null=True)
    almacen_contraparte = serializers.UUIDField(required=False, allow_null=True)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    lineas = _LineaInputSerializer(many=True)


# ── Reabastecimiento y Lotes opt-in (Plan 08 §B.3) ────────────────────────────


class ReglaReabastecimientoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)
    producto_sku = serializers.CharField(source="id_producto.sku", read_only=True, allow_null=True)
    almacen_nombre = serializers.CharField(source="id_almacen.nombre_almacen", read_only=True)
    almacen_origen_nombre = serializers.CharField(
        source="id_almacen_origen.nombre_almacen", read_only=True, allow_null=True
    )
    proveedor_nombre = serializers.CharField(
        source="id_proveedor_preferido.razon_social", read_only=True, allow_null=True
    )

    class Meta:
        model = ReglaReabastecimiento
        fields = [
            "id_regla",
            "id_empresa",
            "id_producto",
            "producto_nombre",
            "producto_sku",
            "id_variante",
            "id_almacen",
            "almacen_nombre",
            "stock_minimo",
            "stock_maximo",
            "cantidad_multiplo",
            "ruta",
            "id_proveedor_preferido",
            "proveedor_nombre",
            "id_almacen_origen",
            "almacen_origen_nombre",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_regla", "id_empresa", "fecha_creacion", "fecha_actualizacion"]
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        visibles = empresas_visibles_contexto(self)
        empresa_ref = empresa_efectiva_contexto(self)

        producto = attrs["id_producto"] if "id_producto" in attrs else getattr(self.instance, "id_producto", None)
        variante = attrs["id_variante"] if "id_variante" in attrs else getattr(self.instance, "id_variante", None)
        almacen = attrs["id_almacen"] if "id_almacen" in attrs else getattr(self.instance, "id_almacen", None)
        proveedor = (
            attrs["id_proveedor_preferido"]
            if "id_proveedor_preferido" in attrs
            else getattr(self.instance, "id_proveedor_preferido", None)
        )
        almacen_origen = (
            attrs["id_almacen_origen"]
            if "id_almacen_origen" in attrs
            else getattr(self.instance, "id_almacen_origen", None)
        )

        validar_fk_empresa(producto, "id_producto", empresa_ref, visibles, etiqueta="Producto")
        validar_fk_empresa(almacen, "id_almacen", empresa_ref, visibles, etiqueta="Almacén")
        validar_fk_empresa(proveedor, "id_proveedor_preferido", empresa_ref, visibles, etiqueta="Proveedor preferido")
        validar_fk_empresa(almacen_origen, "id_almacen_origen", empresa_ref, visibles, etiqueta="Almacén origen")

        if variante is not None:
            validar_fk_empresa(variante.id_producto, "id_variante", empresa_ref, visibles, etiqueta="Variante")
            if producto is not None and variante.id_producto_id != producto.pk:
                raise serializers.ValidationError({"id_variante": "La variante no pertenece al producto indicado."})

        stock_min = attrs.get("stock_minimo", getattr(self.instance, "stock_minimo", Decimal("0")))
        stock_max = attrs.get("stock_maximo", getattr(self.instance, "stock_maximo", Decimal("0")))
        multiplo = attrs.get("cantidad_multiplo", getattr(self.instance, "cantidad_multiplo", Decimal("1")))
        if stock_min is not None and Decimal(str(stock_min)) < 0:
            raise serializers.ValidationError({"stock_minimo": "El stock mínimo no puede ser negativo."})
        if stock_min is not None and stock_max is not None and Decimal(str(stock_max)) < Decimal(str(stock_min)):
            raise serializers.ValidationError(
                {"stock_maximo": "El stock máximo debe ser mayor o igual al stock mínimo."}
            )
        if multiplo is not None and Decimal(str(multiplo)) <= 0:
            raise serializers.ValidationError({"cantidad_multiplo": "La cantidad múltiplo debe ser mayor a cero."})

        ruta = attrs.get("ruta", getattr(self.instance, "ruta", "COMPRA"))
        if almacen_origen is not None and almacen is not None and almacen_origen.pk == almacen.pk:
            raise serializers.ValidationError(
                {"id_almacen_origen": "El almacén origen y destino deben ser distintos."}
            )
        if ruta == "TRANSFERENCIA" and almacen_origen is None:
            raise serializers.ValidationError(
                {"id_almacen_origen": "La ruta TRANSFERENCIA requiere indicar id_almacen_origen."}
            )

        activo = attrs.get("activo", getattr(self.instance, "activo", True))
        if activo and empresa_ref and producto is not None and almacen is not None:
            qs = ReglaReabastecimiento.objects.filter(
                id_empresa_id=empresa_ref,
                id_producto=producto,
                id_variante=variante,
                id_almacen=almacen,
                activo=True,
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "Ya existe una regla de reabastecimiento activa para este producto, variante y almacén."
                )
        return attrs


class LoteProductoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)
    producto_sku = serializers.CharField(source="id_producto.sku", read_only=True, allow_null=True)
    almacen_nombre = serializers.CharField(source="id_almacen.nombre_almacen", read_only=True)
    cantidad_libre = serializers.SerializerMethodField()

    class Meta:
        model = LoteProducto
        fields = [
            "id_lote",
            "id_empresa",
            "id_producto",
            "producto_nombre",
            "producto_sku",
            "id_variante",
            "id_almacen",
            "almacen_nombre",
            "numero_lote",
            "fecha_fabricacion",
            "fecha_vencimiento",
            "cantidad_disponible",
            "cantidad_reservada",
            "cantidad_libre",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_lote",
            "id_empresa",
            "cantidad_disponible",
            "cantidad_reservada",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        validators = []

    def get_cantidad_libre(self, obj: LoteProducto) -> str:
        libre = (obj.cantidad_disponible or Decimal("0")) - (obj.cantidad_reservada or Decimal("0"))
        return str(libre.quantize(Decimal("0.0001")))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        visibles = empresas_visibles_contexto(self)
        empresa_ref = empresa_efectiva_contexto(self)

        if self.instance is not None:
            if "id_producto" in attrs and getattr(attrs["id_producto"], "pk", None) != self.instance.id_producto_id:
                raise serializers.ValidationError(
                    {"id_producto": "No se puede cambiar el producto de un lote existente."}
                )
            if "id_variante" in attrs:
                nueva_var = attrs["id_variante"].pk if attrs["id_variante"] is not None else None
                if nueva_var != self.instance.id_variante_id:
                    raise serializers.ValidationError(
                        {"id_variante": "No se puede cambiar la variante de un lote existente."}
                    )
            if "id_almacen" in attrs and getattr(attrs["id_almacen"], "pk", None) != self.instance.id_almacen_id:
                raise serializers.ValidationError(
                    {"id_almacen": "No se puede cambiar el almacén de un lote existente."}
                )
            if (
                "activo" in attrs
                and not attrs["activo"]
                and (
                    (self.instance.cantidad_disponible or Decimal("0")) > 0
                    or (self.instance.cantidad_reservada or Decimal("0")) > 0
                )
            ):
                raise serializers.ValidationError(
                    {"activo": "No se puede desactivar un lote con cantidad disponible o reservada."}
                )

        producto = attrs["id_producto"] if "id_producto" in attrs else getattr(self.instance, "id_producto", None)
        variante = attrs["id_variante"] if "id_variante" in attrs else getattr(self.instance, "id_variante", None)
        almacen = attrs["id_almacen"] if "id_almacen" in attrs else getattr(self.instance, "id_almacen", None)

        validar_fk_empresa(producto, "id_producto", empresa_ref, visibles, etiqueta="Producto")
        validar_fk_empresa(almacen, "id_almacen", empresa_ref, visibles, etiqueta="Almacén")
        if variante is not None:
            validar_fk_empresa(variante.id_producto, "id_variante", empresa_ref, visibles, etiqueta="Variante")
            if producto is not None and variante.id_producto_id != producto.pk:
                raise serializers.ValidationError({"id_variante": "La variante no pertenece al producto indicado."})

        if "numero_lote" in attrs:
            numero_limpio = str(attrs["numero_lote"] or "").strip()
            if not numero_limpio:
                raise serializers.ValidationError({"numero_lote": "El número de lote no puede estar vacío."})
            attrs["numero_lote"] = numero_limpio
        else:
            numero_limpio = getattr(self.instance, "numero_lote", "")

        fecha_fab = attrs.get("fecha_fabricacion", getattr(self.instance, "fecha_fabricacion", None))
        fecha_ven = attrs.get("fecha_vencimiento", getattr(self.instance, "fecha_vencimiento", None))
        if fecha_fab and fecha_ven and fecha_ven < fecha_fab:
            raise serializers.ValidationError(
                {"fecha_vencimiento": "La fecha de vencimiento no puede ser anterior a la de fabricación."}
            )

        if empresa_ref and producto is not None and almacen is not None and numero_limpio:
            qs = LoteProducto.objects.filter(
                id_empresa_id=empresa_ref,
                id_producto=producto,
                id_variante=variante,
                id_almacen=almacen,
                numero_lote=numero_limpio,
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"numero_lote": f"Ya existe el lote '{numero_limpio}' para este producto y almacén."}
                )
        return attrs


class EvaluarReabastecimientoInputSerializer(serializers.Serializer):
    almacen = serializers.UUIDField(required=False, allow_null=True)
    incluir_ok = serializers.BooleanField(required=False, default=False)


class EvaluarReabastecimientoItemSerializer(serializers.Serializer):
    id_regla = serializers.UUIDField()
    id_producto = serializers.UUIDField()
    producto_nombre = serializers.CharField()
    producto_sku = serializers.CharField(allow_blank=True)
    id_variante = serializers.UUIDField(allow_null=True)
    id_almacen = serializers.UUIDField()
    almacen_nombre = serializers.CharField()
    ruta = serializers.CharField()
    id_proveedor_preferido = serializers.UUIDField(allow_null=True)
    id_almacen_origen = serializers.UUIDField(allow_null=True)
    stock_disponible = serializers.CharField()
    cantidad_comprometida = serializers.CharField()
    cantidad_en_transito = serializers.CharField()
    stock_libre = serializers.CharField()
    stock_proyectado = serializers.CharField()
    stock_minimo = serializers.CharField()
    stock_maximo = serializers.CharField()
    cantidad_multiplo = serializers.CharField()
    requiere_reabastecimiento = serializers.BooleanField()
    deficit = serializers.CharField()
    cantidad_sugerida = serializers.CharField()


class EvaluarReabastecimientoResponseSerializer(serializers.Serializer):
    resultados = EvaluarReabastecimientoItemSerializer(many=True)


class GenerarBorradorInputSerializer(serializers.Serializer):
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    fecha_necesidad = serializers.DateField(required=False, allow_null=True)


class GenerarBorradorResponseSerializer(serializers.Serializer):
    ruta = serializers.CharField()
    tipo_documento = serializers.CharField()
    id_documento = serializers.UUIDField()
    numero = serializers.CharField()
    estado = serializers.CharField()
    cantidad = serializers.CharField()
    lista_materiales_id = serializers.UUIDField(required=False, allow_null=True)
