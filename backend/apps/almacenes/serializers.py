from decimal import Decimal

from rest_framework import serializers

from apps.core.serializer_mixins import (
    empresa_efectiva_contexto,
    empresas_visibles_contexto,
    validar_fk_empresa,
)

from .models import Almacen, StockUbicacion, UbicacionAlmacen


class AlmacenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Almacen
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_almacen",
            "nombre_almacen",
            "codigo_almacen",
            "direccion",
            "usa_ubicaciones",
            "referencia_externa",
            "documento_json",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_sucursal",
        ]
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and "id_empresa" in attrs:
            nueva_emp = attrs["id_empresa"]
            if nueva_emp is None or nueva_emp.pk != self.instance.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_empresa": "No se puede cambiar la empresa de un almacén existente."}
                )
        emp = attrs["id_empresa"] if "id_empresa" in attrs else getattr(self.instance, "id_empresa", None)
        empresa_ref = str(emp.pk) if emp is not None else empresa_efectiva_contexto(self)
        visibles = empresas_visibles_contexto(self)
        if emp is not None and visibles is not None and str(emp.pk) not in visibles:
            raise serializers.ValidationError({"id_empresa": "Empresa fuera de su alcance."})

        sucursal = attrs["id_sucursal"] if "id_sucursal" in attrs else getattr(self.instance, "id_sucursal", None)
        validar_fk_empresa(sucursal, "id_sucursal", empresa_ref, visibles, etiqueta="Sucursal")

        codigo = attrs.get("codigo_almacen", getattr(self.instance, "codigo_almacen", None))
        if codigo and empresa_ref:
            qs = Almacen.objects.filter(id_empresa_id=empresa_ref, codigo_almacen=codigo)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"codigo_almacen": f"Ya existe un almacén con código '{codigo}' en esta empresa."}
                )
        return attrs


class UbicacionAlmacenSerializer(serializers.ModelSerializer):
    class Meta:
        model = UbicacionAlmacen
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_ubicacion",
            "codigo_ubicacion",
            "nombre_ubicacion",
            "tipo_ubicacion",
            "pasillo",
            "estante",
            "nivel",
            "posicion",
            "capacidad_maxima",
            "unidad_capacidad",
            "temperatura_minima",
            "temperatura_maxima",
            "activo",
            "requiere_autorizacion",
            "observaciones",
            "fecha_creacion",
            "id_empresa",
            "id_almacen",
        ]
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and "id_empresa" in attrs:
            nueva_emp = attrs["id_empresa"]
            if nueva_emp is None or nueva_emp.pk != self.instance.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_empresa": "No se puede cambiar la empresa de una ubicación existente."}
                )
        emp = attrs["id_empresa"] if "id_empresa" in attrs else getattr(self.instance, "id_empresa", None)
        empresa_ref = str(emp.pk) if emp is not None else empresa_efectiva_contexto(self)
        visibles = empresas_visibles_contexto(self)
        if emp is not None and visibles is not None and str(emp.pk) not in visibles:
            raise serializers.ValidationError({"id_empresa": "Empresa fuera de su alcance."})

        almacen = attrs["id_almacen"] if "id_almacen" in attrs else getattr(self.instance, "id_almacen", None)
        if (
            self.instance is not None
            and "id_almacen" in attrs
            and (almacen is None or almacen.pk != self.instance.id_almacen_id)
            and StockUbicacion.objects.filter(id_ubicacion=self.instance).exists()
        ):
            raise serializers.ValidationError(
                {"id_almacen": "No se puede cambiar el almacén de una ubicación que ya posee stock registrado."}
            )
        validar_fk_empresa(almacen, "id_almacen", empresa_ref, visibles, etiqueta="Almacén")

        codigo = attrs.get("codigo_ubicacion", getattr(self.instance, "codigo_ubicacion", None))
        if codigo and almacen is not None:
            qs = UbicacionAlmacen.objects.filter(id_almacen=almacen, codigo_ubicacion=codigo)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"codigo_ubicacion": f"Ya existe una ubicación con código '{codigo}' en este almacén."}
                )
        return attrs


class StockUbicacionSerializer(serializers.ModelSerializer):
    almacen_nombre = serializers.CharField(source="id_almacen.nombre_almacen", read_only=True)
    ubicacion_codigo = serializers.CharField(source="id_ubicacion.codigo_ubicacion", read_only=True)
    ubicacion_nombre = serializers.CharField(source="id_ubicacion.nombre_ubicacion", read_only=True)
    requiere_autorizacion = serializers.BooleanField(source="id_ubicacion.requiere_autorizacion", read_only=True)
    producto_nombre = serializers.CharField(source="id_producto.nombre_producto", read_only=True)
    producto_sku = serializers.CharField(source="id_producto.sku", read_only=True, allow_null=True)
    cantidad_libre = serializers.SerializerMethodField()

    class Meta:
        model = StockUbicacion
        fields = [
            "id_stock_ubicacion",
            "id_empresa",
            "id_almacen",
            "almacen_nombre",
            "id_ubicacion",
            "ubicacion_codigo",
            "ubicacion_nombre",
            "requiere_autorizacion",
            "id_producto",
            "producto_nombre",
            "producto_sku",
            "id_variante",
            "cantidad_disponible",
            "cantidad_reservada",
            "cantidad_libre",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_stock_ubicacion",
            "id_empresa",
            "cantidad_reservada",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        validators = []

    def get_cantidad_libre(self, obj: StockUbicacion) -> str:
        libre = (obj.cantidad_disponible or Decimal("0")) - (obj.cantidad_reservada or Decimal("0"))
        return str(libre.quantize(Decimal("0.0001")))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        visibles = empresas_visibles_contexto(self)
        empresa_ref = empresa_efectiva_contexto(self)

        almacen = attrs["id_almacen"] if "id_almacen" in attrs else getattr(self.instance, "id_almacen", None)
        ubicacion = attrs["id_ubicacion"] if "id_ubicacion" in attrs else getattr(self.instance, "id_ubicacion", None)
        producto = attrs["id_producto"] if "id_producto" in attrs else getattr(self.instance, "id_producto", None)
        variante = attrs["id_variante"] if "id_variante" in attrs else getattr(self.instance, "id_variante", None)

        validar_fk_empresa(almacen, "id_almacen", empresa_ref, visibles, etiqueta="Almacén")
        validar_fk_empresa(ubicacion, "id_ubicacion", empresa_ref, visibles, etiqueta="Ubicación")
        validar_fk_empresa(producto, "id_producto", empresa_ref, visibles, etiqueta="Producto")

        if variante is not None:
            validar_fk_empresa(
                variante.id_producto,
                "id_variante",
                empresa_ref,
                visibles,
                etiqueta="Variante",
            )
            if producto is not None and variante.id_producto_id != producto.pk:
                raise serializers.ValidationError({"id_variante": "La variante no pertenece al producto indicado."})

        if almacen is not None and not almacen.usa_ubicaciones:
            raise serializers.ValidationError({"id_almacen": "El almacén debe tener habilitado usa_ubicaciones=True."})
        if almacen is not None and ubicacion is not None and ubicacion.id_almacen_id != almacen.pk:
            raise serializers.ValidationError({"id_ubicacion": "La ubicación no pertenece al almacén indicado."})

        disp = attrs.get("cantidad_disponible", getattr(self.instance, "cantidad_disponible", Decimal("0")))
        if disp is not None and Decimal(str(disp)) < 0:
            raise serializers.ValidationError({"cantidad_disponible": "La cantidad disponible no puede ser negativa."})

        if empresa_ref and almacen is not None and ubicacion is not None and producto is not None:
            qs = StockUbicacion.objects.filter(
                id_empresa_id=empresa_ref,
                id_almacen=almacen,
                id_ubicacion=ubicacion,
                id_producto=producto,
                id_variante=variante,
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "Ya existe un saldo registrado para este producto y ubicación. Use transferir o reservar."
                )
        return attrs


class TransferirUbicacionInputSerializer(serializers.Serializer):
    id_almacen = serializers.UUIDField()
    id_ubicacion_origen = serializers.UUIDField()
    id_ubicacion_destino = serializers.UUIDField()
    id_producto = serializers.UUIDField()
    id_variante = serializers.UUIDField(required=False, allow_null=True)
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.0001"))
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")


class TransferirUbicacionResponseSerializer(serializers.Serializer):
    origen = StockUbicacionSerializer()
    destino = StockUbicacionSerializer()
    id_movimiento = serializers.UUIDField()
    tipo_movimiento = serializers.CharField()


class ReservarUbicacionInputSerializer(serializers.Serializer):
    id_almacen = serializers.UUIDField()
    id_ubicacion = serializers.UUIDField()
    id_producto = serializers.UUIDField()
    id_variante = serializers.UUIDField(required=False, allow_null=True)
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.0001"))
    liberar = serializers.BooleanField(required=False, default=False)
