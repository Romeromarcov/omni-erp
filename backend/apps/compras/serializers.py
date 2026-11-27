from decimal import Decimal

from rest_framework import serializers

from apps.core.viewsets import get_empresa_primaria, get_empresas_visible

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


def _empresas_visibles_contexto(serializer) -> set[str] | None:
    request = serializer.context.get("request") if hasattr(serializer, "context") else None
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return {str(pk) for pk in get_empresas_visible(user).values_list("pk", flat=True)}
    return None


def _empresa_efectiva_contexto(serializer) -> str | None:
    """Devuelve el UUID (str) de la empresa efectiva del serializer, alineado a EmpresaInjectMixin."""
    if getattr(serializer, "instance", None) is not None:
        return str(serializer.instance.id_empresa_id)
    request = serializer.context.get("request") if hasattr(serializer, "context") else None
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        primaria = get_empresa_primaria(user)
        if primaria is None:
            raise serializers.ValidationError({"id_empresa": "El usuario no tiene empresa asignada."})
        return str(primaria.pk)
    return None


def _validar_fk_empresa(
    obj,
    campo: str,
    empresa_ref: str | None,
    visibles: set[str] | None,
    *,
    etiqueta: str,
) -> None:
    if obj is None:
        return
    obj_emp = str(obj.id_empresa_id)
    if visibles is not None and obj_emp not in visibles:
        raise serializers.ValidationError({campo: f"{etiqueta} fuera de su empresa."})
    if empresa_ref is not None and obj_emp != empresa_ref:
        raise serializers.ValidationError({campo: f"{etiqueta} no pertenece a la empresa del documento."})


def _validar_unicidad_empresa(
    modelo,
    campo: str,
    valor: str | None,
    empresa_ref: str | None,
    instance=None,
) -> None:
    if not valor or not empresa_ref:
        return
    qs = modelo.objects.filter(id_empresa_id=empresa_ref, **{campo: valor})
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise serializers.ValidationError({campo: f"Ya existe un registro con {campo} '{valor}'."})


class OrdenCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenCompra
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_orden_compra", "fecha_creacion")

    def validate_ambito(self, value):
        if self.instance is not None and self.instance.estado != "BORRADOR" and value != self.instance.ambito:
            raise serializers.ValidationError(
                "No se puede cambiar el ámbito de una orden de compra después de BORRADOR."
            )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        prov = attrs["id_proveedor"] if "id_proveedor" in attrs else getattr(self.instance, "id_proveedor", None)
        almacen = (
            attrs["id_almacen_destino"]
            if "id_almacen_destino" in attrs
            else getattr(self.instance, "id_almacen_destino", None)
        )
        oferta = (
            attrs["id_oferta_origen"]
            if "id_oferta_origen" in attrs
            else getattr(self.instance, "id_oferta_origen", None)
        )

        visibles = _empresas_visibles_contexto(self)
        empresa_ref = _empresa_efectiva_contexto(self)
        if empresa_ref is None and prov is not None:
            empresa_ref = str(prov.id_empresa_id)

        _validar_unicidad_empresa(
            OrdenCompra,
            "numero_orden",
            attrs.get("numero_orden"),
            empresa_ref,
            self.instance,
        )
        _validar_fk_empresa(prov, "id_proveedor", empresa_ref, visibles, etiqueta="Proveedor")
        _validar_fk_empresa(almacen, "id_almacen_destino", empresa_ref, visibles, etiqueta="Almacén destino")
        if oferta is not None:
            _validar_fk_empresa(
                oferta.id_solicitud_cotizacion,
                "id_oferta_origen",
                empresa_ref,
                visibles,
                etiqueta="Oferta origen",
            )

        return attrs


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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        orden = (
            attrs["id_orden_compra"] if "id_orden_compra" in attrs else getattr(self.instance, "id_orden_compra", None)
        )
        ambito = attrs.get("ambito", getattr(self.instance, "ambito", None))
        if orden is not None and ambito is not None and ambito != orden.ambito:
            raise serializers.ValidationError(
                {"ambito": "El ámbito de la recepción debe coincidir con el ámbito de la orden de compra."}
            )
        return attrs


class FacturaCompraSerializer(serializers.ModelSerializer):
    ambito_display = serializers.CharField(source="get_ambito_display", read_only=True)

    class Meta:
        model = FacturaCompra
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915);
        # excluye referencia_externa y documento_json (SEC-NEW-3).
        fields = [
            "id_factura_compra",
            "id_empresa",
            "id_orden_compra",
            "id_proveedor",
            "id_recepcion",
            "numero_factura",
            "fecha_emision",
            "monto_total",
            "ambito",
            "ambito_display",
            "observaciones",
            "activo",
            "fecha_creacion",
        ]
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_factura_compra", "fecha_creacion")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        orden = (
            attrs["id_orden_compra"] if "id_orden_compra" in attrs else getattr(self.instance, "id_orden_compra", None)
        )
        prov = attrs["id_proveedor"] if "id_proveedor" in attrs else getattr(self.instance, "id_proveedor", None)
        recepcion = attrs["id_recepcion"] if "id_recepcion" in attrs else getattr(self.instance, "id_recepcion", None)

        visibles = _empresas_visibles_contexto(self)
        empresa_ref = _empresa_efectiva_contexto(self)
        if empresa_ref is None:
            if orden is not None:
                empresa_ref = str(orden.id_empresa_id)
            elif prov is not None:
                empresa_ref = str(prov.id_empresa_id)
            elif recepcion is not None:
                empresa_ref = str(recepcion.id_empresa_id)

        _validar_unicidad_empresa(
            FacturaCompra,
            "numero_factura",
            attrs.get("numero_factura"),
            empresa_ref,
            self.instance,
        )
        _validar_fk_empresa(orden, "id_orden_compra", empresa_ref, visibles, etiqueta="Orden de compra")
        _validar_fk_empresa(prov, "id_proveedor", empresa_ref, visibles, etiqueta="Proveedor")
        _validar_fk_empresa(recepcion, "id_recepcion", empresa_ref, visibles, etiqueta="Recepción")

        if orden is None and prov is None:
            raise serializers.ValidationError(
                {"id_proveedor": "Debe indicar un proveedor o una orden de compra asociada."}
            )
        if orden is not None and prov is not None and orden.id_proveedor_id != prov.pk:
            raise serializers.ValidationError(
                {"id_proveedor": "El proveedor indicado no coincide con el proveedor de la orden de compra."}
            )
        if orden is not None and prov is None:
            attrs["id_proveedor"] = orden.id_proveedor

        ambito_eff = attrs.get("ambito", getattr(self.instance, "ambito", None)) or "FISCAL"
        origen_gerencial = (recepcion is not None and recepcion.ambito == "GERENCIAL") or (
            orden is not None and orden.ambito == "GERENCIAL"
        )
        if origen_gerencial and ambito_eff == "FISCAL":
            raise serializers.ValidationError(
                {"ambito": "No se puede emitir una factura de compra FISCAL sobre una recepción u orden GERENCIAL."}
            )

        return attrs


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
        # [B-4]: estado solo transiciona via enviar-aprobacion / confirmar-aprobacion.
        read_only_fields = ("id_empresa", "id_requisicion", "estado", "fecha_creacion")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        visibles = _empresas_visibles_contexto(self)
        empresa_ref = _empresa_efectiva_contexto(self)
        _validar_unicidad_empresa(
            RequisicionCompra,
            "numero_requisicion",
            attrs.get("numero_requisicion"),
            empresa_ref,
            self.instance,
        )
        dep = (
            attrs["id_departamento"] if "id_departamento" in attrs else getattr(self.instance, "id_departamento", None)
        )
        _validar_fk_empresa(dep, "id_departamento", empresa_ref, visibles, etiqueta="Departamento")
        sol = attrs["id_solicitante"] if "id_solicitante" in attrs else getattr(self.instance, "id_solicitante", None)
        if (
            sol is not None
            and empresa_ref is not None
            and not getattr(sol, "es_superusuario_omni", False)
            and not sol.empresas.filter(pk=empresa_ref).exists()
        ):
            raise serializers.ValidationError(
                {"id_solicitante": "El usuario solicitante no pertenece a la empresa de la requisición."}
            )
        return attrs


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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        req = attrs["id_requisicion"] if "id_requisicion" in attrs else getattr(self.instance, "id_requisicion", None)
        prod = attrs["id_producto"] if "id_producto" in attrs else getattr(self.instance, "id_producto", None)
        visibles = _empresas_visibles_contexto(self)
        empresa_ref = str(req.id_empresa_id) if req is not None else None
        _validar_fk_empresa(req, "id_requisicion", None, visibles, etiqueta="Requisición")
        _validar_fk_empresa(prod, "id_producto", empresa_ref, visibles, etiqueta="Producto")
        return attrs


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
            "requisiciones",
            "proveedores_invitados",
            "fecha_creacion",
            "id_empresa",
        ]
        # H-API-2: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_solicitud_cotizacion", "fecha_creacion")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        fecha_sol = attrs.get("fecha_solicitud", getattr(self.instance, "fecha_solicitud", None))
        fecha_venc = attrs.get("fecha_vencimiento", getattr(self.instance, "fecha_vencimiento", None))
        if fecha_sol and fecha_venc and fecha_venc < fecha_sol:
            raise serializers.ValidationError(
                {"fecha_vencimiento": "La fecha de vencimiento no puede ser anterior a la fecha de solicitud."}
            )

        visibles = _empresas_visibles_contexto(self)
        empresa_ref = _empresa_efectiva_contexto(self)
        _validar_unicidad_empresa(
            SolicitudCotizacion,
            "numero_solicitud",
            attrs.get("numero_solicitud"),
            empresa_ref,
            self.instance,
        )

        requisiciones = attrs.get("requisiciones")
        if requisiciones is not None:
            for req in requisiciones:
                req_emp = str(req.id_empresa_id)
                if visibles is not None and req_emp not in visibles:
                    raise serializers.ValidationError({"requisiciones": "Requisición fuera de su empresa."})
                if empresa_ref is None:
                    empresa_ref = req_emp
                elif req_emp != empresa_ref:
                    raise serializers.ValidationError(
                        {"requisiciones": "Todas las requisiciones deben pertenecer a la empresa de la solicitud."}
                    )

        proveedores = attrs.get("proveedores_invitados")
        if proveedores is not None:
            for prov in proveedores:
                prov_emp = str(prov.id_empresa_id)
                if visibles is not None and prov_emp not in visibles:
                    raise serializers.ValidationError({"proveedores_invitados": "Proveedor fuera de su empresa."})
                if empresa_ref is None:
                    empresa_ref = prov_emp
                elif prov_emp != empresa_ref:
                    raise serializers.ValidationError(
                        {
                            "proveedores_invitados": "Los proveedores invitados deben pertenecer a la empresa de la solicitud."
                        }
                    )

        return attrs


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


# ── Serializers de entrada/respuesta para acciones Source-to-PO (OpenAPI) ──────


class CrearRfqDesdeRequisicionesInputSerializer(serializers.Serializer):
    requisicion_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    proveedores_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    fecha_vencimiento = serializers.DateField()
    numero_solicitud = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")


class AdjudicacionParcialItemSerializer(serializers.Serializer):
    id_producto = serializers.UUIDField()
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.0001"))


class AdjudicarOfertaInputSerializer(serializers.Serializer):
    id_almacen_destino = serializers.UUIDField()
    rechazar_competidoras = serializers.BooleanField(required=False, default=True)
    adjudicacion_parcial = AdjudicacionParcialItemSerializer(many=True, required=False, allow_null=True)


class AdjudicarOfertaResponseSerializer(serializers.Serializer):
    id_orden_compra = serializers.UUIDField()
    numero_orden = serializers.CharField()
    estado_orden = serializers.CharField()
    monto_total = serializers.CharField()
    oferta_id = serializers.UUIDField()
    oferta_estado = serializers.CharField()
    rfq_id = serializers.UUIDField()
    rfq_estado = serializers.CharField()
    lineas = serializers.IntegerField()


class OfertaResumenComparativoSerializer(serializers.Serializer):
    id_oferta = serializers.UUIDField()
    numero_oferta = serializers.CharField()
    id_proveedor = serializers.UUIDField()
    proveedor_nombre = serializers.CharField()
    estado = serializers.CharField()
    monto_total = serializers.CharField()
    tiempo_entrega = serializers.CharField(allow_blank=True)
    condiciones_pago = serializers.CharField(allow_blank=True)
    es_mejor_total = serializers.BooleanField()


class CotizacionComparadaSerializer(serializers.Serializer):
    id_oferta = serializers.UUIDField()
    id_proveedor = serializers.UUIDField()
    proveedor_nombre = serializers.CharField()
    cantidad = serializers.CharField(allow_null=True)
    precio_unitario = serializers.CharField(allow_null=True)
    subtotal = serializers.CharField(allow_null=True)
    tiempo_entrega = serializers.CharField(allow_null=True, allow_blank=True)
    es_mejor_precio = serializers.BooleanField()


class ProductoComparadoSerializer(serializers.Serializer):
    id_producto = serializers.UUIDField()
    producto_nombre = serializers.CharField()
    sku = serializers.CharField(allow_blank=True)
    cantidad_solicitada = serializers.CharField()
    especificaciones = serializers.CharField(allow_blank=True)
    mejor_precio_unitario = serializers.CharField(allow_null=True)
    cotizaciones = CotizacionComparadaSerializer(many=True)


class CompararOfertasResponseSerializer(serializers.Serializer):
    rfq_id = serializers.UUIDField()
    numero_solicitud = serializers.CharField()
    estado = serializers.CharField()
    fecha_solicitud = serializers.CharField()
    fecha_vencimiento = serializers.CharField()
    mejor_oferta_id = serializers.UUIDField(allow_null=True)
    ofertas = OfertaResumenComparativoSerializer(many=True)
    productos = ProductoComparadoSerializer(many=True)
