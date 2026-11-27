import uuid

from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.viewsets import (
    BaseModelViewSet,
    EmpresaInjectMixin,
    filtrar_ambito_queryset,
    get_empresas_visible,
)

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
from .serializers import (
    AdjudicarOfertaInputSerializer,
    AdjudicarOfertaResponseSerializer,
    CompararOfertasResponseSerializer,
    CrearRfqDesdeRequisicionesInputSerializer,
    DetalleFacturaCompraSerializer,
    DetalleOfertaProveedorSerializer,
    DetalleOrdenCompraSerializer,
    DetalleRecepcionMercanciaSerializer,
    DetalleRequisicionCompraSerializer,
    DetalleSolicitudCotizacionSerializer,
    FacturaCompraSerializer,
    OfertaProveedorSerializer,
    OrdenCompraSerializer,
    RecepcionMercanciaSerializer,
    RequisicionCompraSerializer,
    SolicitudCotizacionSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


def _validar_uuid(valor: str, campo: str) -> str:
    limpio = str(valor).replace("\x00", "").strip()
    try:
        return str(uuid.UUID(limpio))
    except (ValueError, TypeError) as exc:
        raise ValidationError({campo: f"'{valor}' no es un UUID válido."}) from exc


class _NulSafeFilterMixin:
    """Rechaza bytes NUL en query params (``?search=``, ``?ordering=``, etc.) con HTTP 400."""

    def filter_queryset(self, queryset):
        request = getattr(self, "request", None)
        if request is not None:
            for key, values in request.query_params.lists():
                if "\x00" in str(key):
                    raise ValidationError({"error": "Parámetro de consulta inválido."})
                for val in values:
                    if isinstance(val, str) and "\x00" in val:
                        raise ValidationError({key: "Parámetro de consulta inválido."})
        return super().filter_queryset(queryset)


class OrdenCompraViewSet(_NulSafeFilterMixin, EmpresaInjectMixin, BaseModelViewSet):  # H-API-2
    queryset = OrdenCompra.objects.all()
    serializer_class = OrdenCompraSerializer
    search_fields = ["numero_orden", "observaciones", "id_proveedor__razon_social"]
    ordering_fields = ["fecha_orden", "numero_orden", "estado", "fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1
        return filtrar_ambito_queryset(
            OrdenCompra.objects.filter(id_empresa__in=_empresas(self.request)),
            self.request,
        )

    @action(detail=True, methods=["post"], url_path="aprobar")
    def aprobar(self, request, pk=None):
        """POST /ordenes-compra/{pk}/aprobar/ — Aprueba una OC en estado BORRADOR/ENVIADA."""
        from .services import CompraError, aprobar_orden_compra

        oc = self.get_object()
        try:
            aprobar_orden_compra(oc, request.user)
        except CompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response({"detail": "Orden aprobada.", "estado": oc.estado})


class DetalleOrdenCompraViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = DetalleOrdenCompra.objects.all()
    serializer_class = DetalleOrdenCompraSerializer
    search_fields = ["observaciones", "id_producto__nombre_producto"]
    ordering_fields = ["cantidad", "precio_unitario", "subtotal"]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleOrdenCompra.objects.filter(id_orden_compra__id_empresa__in=_empresas(self.request))


class RecepcionMercanciaViewSet(_NulSafeFilterMixin, EmpresaInjectMixin, BaseModelViewSet):  # H-API-2
    queryset = RecepcionMercancia.objects.all()
    serializer_class = RecepcionMercanciaSerializer
    search_fields = ["observaciones", "id_orden_compra__numero_orden"]
    ordering_fields = ["fecha_recepcion", "monto_total", "fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1
        return filtrar_ambito_queryset(
            RecepcionMercancia.objects.filter(id_empresa__in=_empresas(self.request)),
            self.request,
        )

    @action(detail=False, methods=["post"], url_path="recepcionar")
    def recepcionar(self, request):
        """
        POST /recepciones-mercancia/recepcionar/ — Registra una recepción de mercancía.

        Body: {
            "orden_compra_id": "<uuid>",
            "almacen_id": "<uuid>",
            "items": [{"producto_id": "<uuid>", "cantidad": 10, "costo_unitario": "25.00"}, ...]
        }
        """
        from apps.almacenes.models import Almacen
        from .models import OrdenCompra
        from .services import CompraError, registrar_recepcion

        oc_id = request.data.get("orden_compra_id")
        almacen_id = request.data.get("almacen_id")
        items_raw = request.data.get("items", [])

        if not oc_id or not almacen_id or not items_raw:
            return Response(
                {"detail": "orden_compra_id, almacen_id e items son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            oc = OrdenCompra.objects.get(pk=oc_id, id_empresa__in=_empresas(request))
            # H-SEC-11: el almacén debe ser de una empresa visible del usuario.
            almacen = Almacen.objects.get(pk=almacen_id, id_empresa__in=_empresas(request))
        except (OrdenCompra.DoesNotExist, Almacen.DoesNotExist):
            return Response(
                {"detail": "Orden de compra o almacén no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Resolve product instances for each item
        from apps.inventario.models import Producto

        items = []
        for it in items_raw:
            try:
                # H-SEC-11: el producto debe ser de una empresa visible del usuario.
                producto = Producto.objects.get(pk=it["producto_id"], id_empresa__in=_empresas(request))
            except (Producto.DoesNotExist, KeyError):
                return Response(
                    {"detail": f"Producto '{it.get('producto_id')}' no encontrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items.append(
                {
                    "producto": producto,
                    "cantidad": it.get("cantidad"),
                    "costo_unitario": it.get("costo_unitario", "0"),
                }
            )

        try:
            resultado = registrar_recepcion(oc, almacen, request.user, items)
        except CompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(
            {
                "recepcion_id": str(resultado["recepcion"].pk),
                "movimientos": len(resultado["movimientos"]),
                "cxp_id": str(resultado["cxp"].pk) if resultado.get("cxp") else None,
                "monto_total": str(resultado["recepcion"].monto_total),
            },
            status=status.HTTP_201_CREATED,
        )


class FacturaCompraViewSet(_NulSafeFilterMixin, EmpresaInjectMixin, BaseModelViewSet):  # H-API-2
    queryset = FacturaCompra.objects.all()
    serializer_class = FacturaCompraSerializer
    filterset_fields = ["ambito", "id_empresa", "id_proveedor", "id_orden_compra"]
    search_fields = ["numero_factura", "observaciones"]
    ordering_fields = ["fecha_emision", "numero_factura", "monto_total", "fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1
        return filtrar_ambito_queryset(
            FacturaCompra.objects.filter(id_empresa__in=_empresas(self.request)),
            self.request,
        )

    @action(detail=False, methods=["post"], url_path="facturar")
    def facturar(self, request):
        """
        POST /facturas-compra/facturar/ — Registra la factura de proveedor sobre una recepción.

        Body: {"recepcion_id": "<uuid>", "numero_factura": "FAC-001", "fecha_emision": "YYYY-MM-DD"}
        """
        from .models import RecepcionMercancia
        from .services import CompraError, registrar_factura_compra

        recepcion_id = request.data.get("recepcion_id")
        numero_factura = request.data.get("numero_factura")

        if not recepcion_id or not numero_factura:
            return Response(
                {"detail": "recepcion_id y numero_factura son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            recepcion = RecepcionMercancia.objects.get(pk=recepcion_id, id_empresa__in=_empresas(request))
        except RecepcionMercancia.DoesNotExist:
            return Response({"detail": "Recepción no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        try:
            resultado = registrar_factura_compra(
                recepcion,
                numero_factura=numero_factura,
                fecha_emision=request.data.get("fecha_emision"),
                usuario=request.user,
                ambito=request.data.get("ambito"),
            )
        except CompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(
            {
                "factura_id": str(resultado["factura"].pk),
                "numero_factura": resultado["factura"].numero_factura,
                "monto_total": str(resultado["factura"].monto_total),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get", "post"], url_path="validar-three-way-matching")
    def validar_three_way_matching(self, request, pk=None):
        """Cruza OrdenCompra ↔ RecepcionMercancia ↔ FacturaCompra (3-Way Matching)."""
        from decimal import Decimal

        from .serializers_supply_chain import ValidarThreeWayMatchingInputSerializer
        from .services_supply_chain import SupplyChainCompraError, validar_three_way_matching

        factura = self.get_object()
        raw = request.data if request.method == "POST" and isinstance(request.data, dict) else {}
        if request.method == "GET":
            for k in ("tolerancia_cantidad_pct", "tolerancia_precio_pct"):
                val = request.query_params.get(k)
                if val is not None:
                    if "\x00" in val:
                        raise ValidationError({k: "Parámetro inválido."})
                    raw = {**raw, k: val}

        ser = ValidarThreeWayMatchingInputSerializer(data=raw)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            res = validar_three_way_matching(
                factura,
                tolerancia_cantidad_pct=vd.get("tolerancia_cantidad_pct", Decimal("0")),
                tolerancia_precio_pct=vd.get("tolerancia_precio_pct", Decimal("1.00")),
            )
        except SupplyChainCompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(res, status=status.HTTP_200_OK)


class RequisicionCompraViewSet(_NulSafeFilterMixin, EmpresaInjectMixin, BaseModelViewSet):  # H-API-2
    queryset = RequisicionCompra.objects.all()
    serializer_class = RequisicionCompraSerializer
    search_fields = ["numero_requisicion", "justificacion", "observaciones"]
    ordering_fields = [
        "fecha_requisicion",
        "fecha_necesidad",
        "numero_requisicion",
        "estado",
        "prioridad",
        "fecha_creacion",
    ]

    def get_queryset(self):
        # R-CODE-1
        qs = RequisicionCompra.objects.filter(id_empresa__in=_empresas(self.request))
        estado = self.request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado.replace("\x00", "").strip())
        return qs

    @swagger_auto_schema(request_body=no_body, responses={200: RequisicionCompraSerializer})
    @action(detail=True, methods=["post"], url_path="enviar-aprobacion")
    def enviar_aprobacion(self, request, pk=None):
        """POST /requisiciones-compra/{pk}/enviar-aprobacion/ — Envía una requisición BORRADOR a aprobación."""
        from apps.gestion_aprobaciones.services import AprobacionError

        from .services import CompraError
        from .services_procurement import enviar_requisicion_aprobacion

        req = self.get_object()
        try:
            actualizada = enviar_requisicion_aprobacion(req, request.user)
        except (CompraError, AprobacionError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(RequisicionCompraSerializer(actualizada).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(request_body=no_body, responses={200: RequisicionCompraSerializer})
    @action(detail=True, methods=["post"], url_path="confirmar-aprobacion")
    def confirmar_aprobacion(self, request, pk=None):
        """POST /requisiciones-compra/{pk}/confirmar-aprobacion/ — Pasa de PENDIENTE a APROBADA tras resolver flujo."""
        from apps.gestion_aprobaciones.services import AprobacionError

        from .services import CompraError
        from .services_procurement import confirmar_aprobacion_requisicion

        req = self.get_object()
        try:
            actualizada = confirmar_aprobacion_requisicion(req, request.user)
        except (CompraError, AprobacionError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(RequisicionCompraSerializer(actualizada).data, status=status.HTTP_200_OK)


class DetalleRequisicionCompraViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = DetalleRequisicionCompra.objects.all()
    serializer_class = DetalleRequisicionCompraSerializer
    search_fields = ["justificacion", "observaciones", "id_producto__nombre_producto"]
    ordering_fields = ["cantidad_solicitada", "precio_estimado"]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleRequisicionCompra.objects.filter(id_requisicion__id_empresa__in=_empresas(self.request))


class SolicitudCotizacionViewSet(_NulSafeFilterMixin, EmpresaInjectMixin, BaseModelViewSet):  # H-API-2
    queryset = SolicitudCotizacion.objects.all()
    serializer_class = SolicitudCotizacionSerializer
    search_fields = ["numero_solicitud", "observaciones"]
    ordering_fields = ["fecha_solicitud", "fecha_vencimiento", "numero_solicitud", "estado", "fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1
        qs = SolicitudCotizacion.objects.filter(id_empresa__in=_empresas(self.request)).prefetch_related(
            "requisiciones", "proveedores_invitados"
        )
        estado = self.request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado.replace("\x00", "").strip())
        return qs

    @swagger_auto_schema(
        request_body=CrearRfqDesdeRequisicionesInputSerializer,
        responses={201: SolicitudCotizacionSerializer},
    )
    @action(detail=False, methods=["post"], url_path="desde-requisiciones")
    def desde_requisiciones(self, request):
        """POST /solicitudes-cotizacion/desde-requisiciones/ — Consolida requisiciones APROBADA en una RFQ."""
        from .services import CompraError
        from .services_procurement import crear_rfq_desde_requisiciones

        serializer = CrearRfqDesdeRequisicionesInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        req_ids = [str(pk) for pk in datos["requisicion_ids"]]
        prov_ids = [str(pk) for pk in datos["proveedores_ids"]]
        empresas = _empresas(request)

        reqs = list(
            RequisicionCompra.objects.filter(pk__in=set(req_ids), id_empresa__in=empresas).select_related("id_empresa")
        )
        if len(reqs) != len(set(req_ids)):
            return Response(
                {"detail": "Una o más requisiciones no encontradas."},
                status=status.HTTP_404_NOT_FOUND,
            )

        empresa = reqs[0].id_empresa
        try:
            rfq = crear_rfq_desde_requisiciones(
                empresa=empresa,
                requisicion_ids=req_ids,
                proveedores_ids=prov_ids,
                fecha_vencimiento=datos["fecha_vencimiento"],
                usuario=request.user,
                observaciones=datos.get("observaciones", ""),
                numero_solicitud=datos.get("numero_solicitud", ""),
            )
        except CompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(SolicitudCotizacionSerializer(rfq).data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(responses={200: CompararOfertasResponseSerializer})
    @action(detail=True, methods=["get"], url_path="comparar-ofertas")
    def comparar_ofertas(self, request, pk=None):
        """GET /solicitudes-cotizacion/{pk}/comparar-ofertas/ — Matriz comparativa lado a lado."""
        from .services_procurement import comparar_ofertas_rfq

        rfq = self.get_object()
        return Response(comparar_ofertas_rfq(rfq), status=status.HTTP_200_OK)


class DetalleSolicitudCotizacionViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = DetalleSolicitudCotizacion.objects.all()
    serializer_class = DetalleSolicitudCotizacionSerializer
    search_fields = ["especificaciones", "observaciones", "id_producto__nombre_producto"]
    ordering_fields = ["cantidad"]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleSolicitudCotizacion.objects.filter(
            id_solicitud_cotizacion__id_empresa__in=_empresas(self.request)
        )


class OfertaProveedorViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = OfertaProveedor.objects.all()
    serializer_class = OfertaProveedorSerializer
    search_fields = ["numero_oferta", "condiciones_pago", "observaciones", "id_proveedor__razon_social"]
    ordering_fields = [
        "fecha_oferta",
        "fecha_vencimiento",
        "numero_oferta",
        "monto_total",
        "estado",
        "fecha_creacion",
    ]

    def get_queryset(self):
        # R-CODE-1 via SolicitudCotizacion parent
        qs = OfertaProveedor.objects.filter(id_solicitud_cotizacion__id_empresa__in=_empresas(self.request))
        estado = self.request.query_params.get("estado")
        solicitud_id = self.request.query_params.get("solicitud")
        if estado:
            qs = qs.filter(estado=estado.replace("\x00", "").strip())
        if solicitud_id:
            qs = qs.filter(id_solicitud_cotizacion_id=_validar_uuid(solicitud_id, "solicitud"))
        return qs

    @swagger_auto_schema(
        request_body=AdjudicarOfertaInputSerializer,
        responses={201: AdjudicarOfertaResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="adjudicar")
    def adjudicar(self, request, pk=None):
        """POST /ofertas-proveedor/{pk}/adjudicar/ — Adjudica total/parcialmente la oferta a una OrdenCompra."""
        from apps.almacenes.models import Almacen

        from .services import CompraError
        from .services_procurement import adjudicar_oferta_a_orden_compra

        oferta = self.get_object()
        serializer = AdjudicarOfertaInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        almacen = Almacen.objects.filter(
            pk=datos["id_almacen_destino"],
            id_empresa__in=_empresas(request),
        ).first()
        if almacen is None:
            return Response({"detail": "Almacén destino no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        parcial = datos.get("adjudicacion_parcial")
        try:
            resultado = adjudicar_oferta_a_orden_compra(
                oferta=oferta,
                almacen_destino=almacen,
                usuario=request.user,
                adjudicacion_parcial=parcial,
                rechazar_competidoras=datos.get("rechazar_competidoras", True),
            )
        except CompraError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        oc = resultado["orden_compra"]
        return Response(
            {
                "id_orden_compra": str(oc.pk),
                "numero_orden": oc.numero_orden,
                "estado_orden": oc.estado,
                "monto_total": str(resultado["monto_total"]),
                "oferta_id": str(resultado["oferta"].pk),
                "oferta_estado": resultado["oferta"].estado,
                "rfq_id": str(resultado["rfq"].pk),
                "rfq_estado": resultado["rfq"].estado,
                "lineas": resultado["lineas"],
            },
            status=status.HTTP_201_CREATED,
        )


class DetalleOfertaProveedorViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = DetalleOfertaProveedor.objects.all()
    serializer_class = DetalleOfertaProveedorSerializer
    search_fields = ["observaciones", "id_producto__nombre_producto"]
    ordering_fields = ["cantidad", "precio_unitario", "subtotal"]

    def get_queryset(self):
        # R-CODE-1 via OfertaProveedor → SolicitudCotizacion
        return DetalleOfertaProveedor.objects.filter(
            id_oferta__id_solicitud_cotizacion__id_empresa__in=_empresas(self.request)
        )


class DetalleRecepcionMercanciaViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = DetalleRecepcionMercancia.objects.all()
    serializer_class = DetalleRecepcionMercanciaSerializer
    search_fields = ["observaciones", "id_producto__nombre_producto"]
    ordering_fields = ["cantidad_esperada", "cantidad_recibida", "costo_unitario", "subtotal"]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleRecepcionMercancia.objects.filter(id_recepcion__id_empresa__in=_empresas(self.request))


class DetalleFacturaCompraViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = DetalleFacturaCompra.objects.all()
    serializer_class = DetalleFacturaCompraSerializer
    search_fields = ["observaciones", "id_producto__nombre_producto"]
    ordering_fields = ["cantidad", "precio_unitario", "subtotal", "total_linea"]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleFacturaCompra.objects.filter(id_factura_compra__id_empresa__in=_empresas(self.request))
