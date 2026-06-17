"""
API de despacho/entrega (R-CODE-7: API-first).

Endpoints (prefijo /api/despacho/):
  GET/POST  despachos/                      — CRUD del encabezado (estado read-only)
  POST      despachos/desde-nota-venta/     — crea despacho desde una venta confirmada
  POST      despachos/{pk}/iniciar-ruta/    — PENDIENTE → EN_RUTA (asigna chofer opcional)
  POST      despachos/{pk}/entregar/        — EN_RUTA → ENTREGADO (receptor/firma)
  POST      despachos/{pk}/devolver/        — EN_RUTA → DEVUELTO (motivo)
  POST      despachos/{pk}/cancelar/        — PENDIENTE → CANCELADO (motivo)
  GET       despachos/{pk}/pdf/             — nota de entrega en PDF
  GET       detalles-despacho/              — líneas (solo lectura; se crean vía servicio)

Filtros de listado: ?estado=, ?id_transportista=, ?id_nota_venta=,
?fecha_desde=YYYY-MM-DD, ?fecha_hasta=YYYY-MM-DD (sobre fecha_despacho).

Los despachos NO se eliminan (DELETE → 405): el ciclo se cierra con
CANCELADO/DEVUELTO para no perder trazabilidad de entregas.
"""

import logging

from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from . import models, serializers
from .services import DespachoError, crear_despacho_desde_nota_venta, transicionar_despacho

logger = logging.getLogger(__name__)


def _empresas(request):
    return get_empresas_visible(request.user)


class DespachoViewSet(BaseModelViewSet):
    queryset = models.Despacho.objects.select_related(
        "id_nota_venta", "id_pedido", "id_almacen_origen", "id_transportista"
    ).prefetch_related("detalles__id_producto", "detalles__id_unidad_medida")
    serializer_class = serializers.DespachoSerializer
    search_fields = ["numero_despacho", "direccion_destino"]
    ordering_fields = ["fecha_despacho", "fecha_creacion", "numero_despacho", "estado_despacho"]

    def get_queryset(self):
        # R-CODE-1: solo despachos de empresas visibles del usuario.
        qs = self.queryset.filter(id_empresa__in=_empresas(self.request))

        params = self.request.query_params
        estado = params.get("estado")
        if estado:
            qs = qs.filter(estado_despacho=estado.upper())
        transportista = params.get("id_transportista")
        if transportista:
            qs = qs.filter(id_transportista=transportista)
        nota_venta = params.get("id_nota_venta")
        if nota_venta:
            qs = qs.filter(id_nota_venta=nota_venta)
        for param, lookup in (
            ("fecha_desde", "fecha_despacho__date__gte"),
            ("fecha_hasta", "fecha_despacho__date__lte"),
        ):
            valor = params.get(param)
            if valor:
                fecha = parse_date(valor)
                if fecha is None:
                    raise ValidationError({param: "Formato de fecha inválido (use YYYY-MM-DD)."})
                qs = qs.filter(**{lookup: fecha})
        return qs

    def perform_create(self, serializer):
        """
        H-API-1: la empresa se deriva del almacén de origen (ya acotado a
        empresas visibles por TenantFKScopeMixin) y el número es el correlativo
        fiscal de esa empresa — nunca se confía en el payload.
        """
        from apps.fiscal.services import siguiente_numero

        almacen = serializer.validated_data["id_almacen_origen"]
        serializer.save(
            id_empresa=almacen.id_empresa,
            numero_despacho=siguiente_numero(almacen.id_empresa, "DESPACHO"),
        )

    def destroy(self, request, *args, **kwargs):
        # Documento operativo: no se borra (trazabilidad); se cancela o devuelve.
        raise MethodNotAllowed(
            "DELETE", detail="Los despachos no se eliminan; use /cancelar/ o /devolver/."
        )

    # ── Crear desde la venta ──────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="desde-nota-venta")
    def desde_nota_venta(self, request):
        """
        POST /api/despacho/despachos/desde-nota-venta/
        Body: {id_nota_venta, almacen_id, direccion_entrega, id_transportista?,
               fecha_entrega_estimada?, observaciones?, lineas?: [{id_producto, cantidad}]}

        Crea un despacho PENDIENTE desde una NotaVenta ENTREGADA/FACTURADA.
        Sin "lineas" despacha todo lo pendiente; con "lineas" permite despacho
        parcial (validado contra lo vendido). No mueve stock (ya salió al
        confirmar la venta).
        """
        from apps.almacenes.models import Almacen
        from apps.rrhh.models import Empleado
        from apps.ventas.models import NotaVenta

        payload = serializers.DespachoDesdeNotaVentaSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        datos = payload.validated_data
        empresas = _empresas(request)

        try:
            nota = NotaVenta.objects.get(
                pk=datos["id_nota_venta"], id_empresa__in=empresas
            )
        except NotaVenta.DoesNotExist:
            raise ValidationError({"id_nota_venta": "Nota de venta no encontrada en sus empresas."})
        try:
            almacen = Almacen.objects.get(pk=datos["almacen_id"], id_empresa__in=empresas)
        except Almacen.DoesNotExist:
            raise ValidationError({"almacen_id": "Almacén no encontrado en sus empresas."})

        transportista = None
        if datos.get("id_transportista"):
            try:
                transportista = Empleado.objects.get(
                    pk=datos["id_transportista"], empresa__in=empresas
                )
            except Empleado.DoesNotExist:
                raise ValidationError(
                    {"id_transportista": "Transportista no encontrado en sus empresas."}
                )

        lineas = datos.get("lineas")
        if lineas is not None:
            lineas = [
                {"id_producto": linea["id_producto"], "cantidad": linea["cantidad"]}
                for linea in lineas
            ]

        try:
            despacho = crear_despacho_desde_nota_venta(
                nota_venta=nota,
                almacen=almacen,
                usuario=request.user,
                direccion_entrega=datos["direccion_entrega"],
                transportista=transportista,
                lineas=lineas,
                fecha_entrega_estimada=datos.get("fecha_entrega_estimada"),
                observaciones=datos.get("observaciones"),
            )
        except DespachoError as exc:
            raise ValidationError(str(exc)) from exc

        serializer = self.get_serializer(despacho)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ── Transiciones de estado ────────────────────────────────────────────────

    def _transicionar(self, request, nuevo_estado, **kwargs):
        despacho = self.get_object()  # 404 si es de otra empresa (R-CODE-1)
        try:
            despacho = transicionar_despacho(despacho, nuevo_estado, request.user, **kwargs)
        except DespachoError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(self.get_serializer(despacho).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="iniciar-ruta")
    def iniciar_ruta(self, request, pk=None):
        """PENDIENTE → EN_RUTA. Body opcional: {id_transportista} (chofer que sale)."""
        from apps.rrhh.models import Empleado

        payload = serializers.IniciarRutaSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        transportista = None
        if payload.validated_data.get("id_transportista"):
            try:
                transportista = Empleado.objects.get(
                    pk=payload.validated_data["id_transportista"],
                    empresa__in=_empresas(request),
                )
            except Empleado.DoesNotExist:
                raise ValidationError(
                    {"id_transportista": "Transportista no encontrado en sus empresas."}
                )
        return self._transicionar(
            request, models.Despacho.ESTADO_EN_RUTA, transportista=transportista
        )

    @action(detail=True, methods=["post"], url_path="entregar")
    def entregar(self, request, pk=None):
        """EN_RUTA → ENTREGADO. Body: {receptor, documento_receptor?, firma_base64?}."""
        payload = serializers.EntregaDespachoSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._transicionar(
            request,
            models.Despacho.ESTADO_ENTREGADO,
            receptor=payload.validated_data["receptor"],
            documento_receptor=payload.validated_data.get("documento_receptor"),
            firma_base64=payload.validated_data.get("firma_base64"),
        )

    @action(detail=True, methods=["post"], url_path="devolver")
    def devolver(self, request, pk=None):
        """EN_RUTA → DEVUELTO. Body: {motivo}. No reingresa stock (DevolucionVenta)."""
        payload = serializers.MotivoDespachoSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._transicionar(
            request, models.Despacho.ESTADO_DEVUELTO, motivo=payload.validated_data["motivo"]
        )

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """PENDIENTE → CANCELADO. Body: {motivo}."""
        payload = serializers.MotivoDespachoSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._transicionar(
            request, models.Despacho.ESTADO_CANCELADO, motivo=payload.validated_data["motivo"]
        )

    # ── Documento ────────────────────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/despacho/despachos/{pk}/pdf/ — nota de entrega en PDF."""
        from django.http import HttpResponse

        from .pdf_nota_entrega import generar_pdf_nota_entrega

        despacho = self.get_object()
        try:
            pdf_bytes = generar_pdf_nota_entrega(despacho)
        except ImportError:
            # SEC-M4 (R-CODE-8): no filtrar el detalle interno al cliente.
            logger.exception("Generación de PDF de nota de entrega no disponible")
            return Response(
                {"error": "Generación de PDF no disponible en este servidor."}, status=503
            )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="nota_entrega_{despacho.numero_despacho}.pdf"'
        )
        return response


class DetalleDespachoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Líneas de despacho — SOLO LECTURA por API: se crean junto con el despacho
    (servicio que valida el cupo contra la venta). Editar líneas sueltas
    permitiría burlar la validación de sobre-despacho; una corrección se hace
    cancelando el despacho y creando otro.
    """

    queryset = models.DetalleDespacho.objects.select_related(
        "id_producto", "id_unidad_medida", "id_despacho"
    ).order_by("id_detalle_despacho")  # uuid7: orden cronológico estable para paginar
    serializer_class = serializers.DetalleDespachoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 — DetalleDespacho no tiene id_empresa directo; llega vía Despacho.
        qs = self.queryset.filter(id_despacho__id_empresa__in=_empresas(self.request))
        despacho = self.request.query_params.get("id_despacho")
        if despacho:
            qs = qs.filter(id_despacho=despacho)
        return qs
