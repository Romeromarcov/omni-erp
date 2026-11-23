"""Vistas API para Logística TMS Inteligente, ePOD y Tracking Público (Plan 09 Fase 6)."""

from __future__ import annotations

from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.almacenes.models import Almacen
from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import (
    ActiveFilterMixin,
    EmpresaInjectMixin,
    NulSafeFilterMixin,
    get_empresa_primaria,
    get_empresas_visible,
    validar_uuid_param,
)

from .delivery_externo import DeliveryExternoError, obtener_proveedor_delivery
from .models import Conductor, Despacho, ParadaEntrega, RutaDespacho, TarifaFlete, Vehiculo, ZonaLogistica
from .serializers_tms import (
    ActualizarGPSVehiculoInputSerializer,
    ConductorSerializer,
    CotizarDeliveryInputSerializer,
    EmitirGuiaSeniatInputSerializer,
    OptimizarVRPInputSerializer,
    ParadaEntregaSerializer,
    RegistrarEPODInputSerializer,
    RutaDespachoSerializer,
    SolicitarDeliveryRutaInputSerializer,
    TarifaFleteSerializer,
    VehiculoSerializer,
    ZonaLogisticaSerializer,
)
from .services_tms import (
    TMSError,
    actualizar_gps_vehiculo,
    cancelar_ruta_despacho,
    consultar_tracking_delivery_ruta,
    emitir_guia_despacho_seniat,
    generar_payload_tracking_whatsapp,
    iniciar_ruta_despacho,
    registrar_epod_parada,
    solicitar_delivery_externo_ruta,
    torre_control_tms,
)
from .services_vrp import VRPError, optimizar_rutas_vrp


def _no_nul(valor: str | None, campo: str) -> str | None:
    if valor is None or valor == "":
        return None
    if "\x00" in str(valor):
        raise ValidationError({campo: "Parámetro inválido."})
    return str(valor).strip()


def _resolver_empresa(request):
    visibles = get_empresas_visible(request.user)
    raw_emp = request.data.get("id_empresa") if isinstance(request.data, dict) else None
    raw_emp = raw_emp or request.query_params.get("empresa")
    if raw_emp:
        uid = validar_uuid_param(str(raw_emp), "id_empresa")
        emp = visibles.filter(pk=uid).first()
        if emp is None:
            raise ValidationError({"id_empresa": "Empresa fuera de su alcance."})
        return emp
    emp = get_empresa_primaria(request.user) or visibles.first()
    if emp is None:
        raise ValidationError({"id_empresa": "Usuario sin empresa asignada."})
    return emp


class _SoftDeleteTMSMixin:
    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=["activo", "fecha_actualizacion"])


class ZonaLogisticaViewSet(
    TenantFKScopeMixin,
    NulSafeFilterMixin,
    ActiveFilterMixin,
    EmpresaInjectMixin,
    _SoftDeleteTMSMixin,
    viewsets.ModelViewSet,
):
    queryset = ZonaLogistica.objects.all()
    serializer_class = ZonaLogisticaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["codigo", "nombre", "ciudad", "estado_provincia"]
    ordering_fields = ["codigo", "nombre", "tarifa_base_usd", "fecha_creacion"]
    ordering = ["nombre"]

    def get_queryset(self):
        return ZonaLogistica.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))


class TarifaFleteViewSet(
    TenantFKScopeMixin,
    NulSafeFilterMixin,
    ActiveFilterMixin,
    EmpresaInjectMixin,
    _SoftDeleteTMSMixin,
    viewsets.ModelViewSet,
):
    queryset = TarifaFlete.objects.all()
    serializer_class = TarifaFleteSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["id_zona__nombre", "tipo_calculo"]
    ordering_fields = ["tipo_calculo", "monto_base_usd", "fecha_creacion"]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        qs = TarifaFlete.objects.filter(id_empresa__in=get_empresas_visible(self.request.user)).select_related(
            "id_zona"
        )
        zona_id = self.request.query_params.get("zona")
        if zona_id:
            qs = qs.filter(id_zona_id=validar_uuid_param(zona_id, "zona"))
        return qs


class VehiculoViewSet(
    TenantFKScopeMixin,
    NulSafeFilterMixin,
    ActiveFilterMixin,
    EmpresaInjectMixin,
    _SoftDeleteTMSMixin,
    viewsets.ModelViewSet,
):
    queryset = Vehiculo.objects.all()
    serializer_class = VehiculoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["placa", "marca_modelo", "tipo_vehiculo"]
    ordering_fields = ["placa", "estado", "capacidad_kg", "fecha_creacion"]
    ordering = ["placa"]

    def get_queryset(self):
        qs = Vehiculo.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
        estado = _no_nul(self.request.query_params.get("estado"), "estado")
        if estado:
            qs = qs.filter(estado=estado.upper())
        return qs

    @swagger_auto_schema(request_body=ActualizarGPSVehiculoInputSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path="actualizar-gps",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def actualizar_gps(self, request, pk=None):
        """Actualiza las coordenadas GPS actuales del vehículo."""
        veh = self.get_object()
        ser = ActualizarGPSVehiculoInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            upd = actualizar_gps_vehiculo(veh, latitud=vd["latitud"], longitud=vd["longitud"])
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(VehiculoSerializer(upd, context={"request": request}).data)


class ConductorViewSet(
    TenantFKScopeMixin,
    NulSafeFilterMixin,
    ActiveFilterMixin,
    EmpresaInjectMixin,
    _SoftDeleteTMSMixin,
    viewsets.ModelViewSet,
):
    queryset = Conductor.objects.all()
    serializer_class = ConductorSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre_completo", "cedula", "telefono"]
    ordering_fields = ["nombre_completo", "disponible", "fecha_creacion"]
    ordering = ["nombre_completo"]

    def get_queryset(self):
        return Conductor.objects.filter(id_empresa__in=get_empresas_visible(self.request.user)).select_related(
            "id_vehiculo_asignado"
        )


class RutaDespachoViewSet(
    TenantFKScopeMixin, NulSafeFilterMixin, ActiveFilterMixin, EmpresaInjectMixin, viewsets.ModelViewSet
):
    queryset = RutaDespacho.objects.all()
    serializer_class = RutaDespachoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["codigo", "referencia_delivery_externo", "guia_numero_control"]
    ordering_fields = ["fecha_ruta", "codigo", "estado", "distancia_estimada_km", "fecha_creacion"]
    ordering = ["-fecha_ruta", "-fecha_creacion"]

    def get_queryset(self):
        qs = (
            RutaDespacho.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
            .select_related("id_almacen_origen", "id_vehiculo", "id_conductor", "id_zona")
            .prefetch_related("paradas__id_despacho")
        )
        estado = _no_nul(self.request.query_params.get("estado"), "estado")
        if estado:
            qs = qs.filter(estado=estado.upper())
        return qs

    def perform_update(self, serializer):
        if serializer.instance.estado != "PLANIFICADA":
            raise ValidationError({"estado": f"No se puede editar una ruta en estado {serializer.instance.estado}."})
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.estado != "PLANIFICADA":
            raise ValidationError({"estado": f"No se puede eliminar una ruta en estado {instance.estado}."})
        instance.activo = False
        instance.save(update_fields=["activo", "fecha_actualizacion"])

    @swagger_auto_schema(request_body=OptimizarVRPInputSerializer)
    @action(
        detail=False,
        methods=["post"],
        url_path="optimizar-vrp",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def optimizar_vrp(self, request):
        """Optimiza rutas multi-vehículo por capacidad y distancia geodésica (NN + 2-opt)."""
        ser = OptimizarVRPInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        empresa = _resolver_empresa(request)

        alm = Almacen.objects.filter(pk=vd["id_almacen_origen"], id_empresa=empresa).first()
        if alm is None:
            return Response({"id_almacen_origen": "Almacén no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        zona = None
        if vd.get("id_zona"):
            zona = ZonaLogistica.objects.filter(pk=vd["id_zona"], id_empresa=empresa).first()
            if zona is None:
                return Response({"id_zona": "Zona logística no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        despachos = list(Despacho.objects.filter(id_empresa=empresa, pk__in=vd["despachos"]))
        if len(despachos) != len(set(vd["despachos"])):
            return Response(
                {"despachos": "Uno o más despachos no existen en la empresa."}, status=status.HTTP_404_NOT_FOUND
            )

        vehiculos = list(Vehiculo.objects.filter(id_empresa=empresa, pk__in=vd["vehiculos"]))
        if len(vehiculos) != len(set(vd["vehiculos"])):
            return Response(
                {"vehiculos": "Uno o más vehículos no existen en la empresa."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            res = optimizar_rutas_vrp(
                empresa=empresa,
                almacen_origen=alm,
                despachos=despachos,
                vehiculos=vehiculos,
                origen_lat=vd["origen_lat"],
                origen_lng=vd["origen_lng"],
                fecha_ruta=vd.get("fecha_ruta"),
                factor_trafico=vd["factor_trafico"],
                zona=zona,
            )
        except VRPError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(
            {
                "rutas_creadas": res["rutas_creadas"],
                "despachos_asignados": res["despachos_asignados"],
                "despachos_no_asignados": res["despachos_no_asignados"],
                "rutas": RutaDespachoSerializer(res["rutas"], many=True, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @swagger_auto_schema(request_body=no_body)
    @idempotent(scope="despacho:iniciar_ruta")
    @action(
        detail=True,
        methods=["post"],
        url_path="iniciar",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def iniciar(self, request, pk=None):
        """Inicia una ruta PLANIFICADA pasando sus despachos a EN_RUTA."""
        ruta = self.get_object()
        try:
            upd = iniciar_ruta_despacho(ruta, request.user)
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(RutaDespachoSerializer(upd, context={"request": request}).data)

    @swagger_auto_schema(request_body=no_body)
    @action(
        detail=True,
        methods=["post"],
        url_path="cancelar",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def cancelar(self, request, pk=None):
        """Cancela una ruta en estado PLANIFICADA."""
        ruta = self.get_object()
        try:
            upd = cancelar_ruta_despacho(ruta)
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(RutaDespachoSerializer(upd, context={"request": request}).data)

    @swagger_auto_schema(request_body=CotizarDeliveryInputSerializer)
    @action(detail=False, methods=["post"], url_path="cotizar-delivery")
    def cotizar_delivery(self, request):
        """Cotiza tarifa y ETA con proveedor externo (Uber Direct / Ridery / Yummy / Simulado)."""
        ser = CotizarDeliveryInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            adapter = obtener_proveedor_delivery(vd["proveedor"])
            res = adapter.cotizar(
                origen_lat=vd["origen_lat"],
                origen_lng=vd["origen_lng"],
                destino_lat=vd["destino_lat"],
                destino_lng=vd["destino_lng"],
                peso_kg=vd["peso_kg"],
            )
        except DeliveryExternoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(res, status=status.HTTP_200_OK)

    @swagger_auto_schema(request_body=SolicitarDeliveryRutaInputSerializer)
    @idempotent(scope="despacho:solicitar_delivery")
    @action(
        detail=True,
        methods=["post"],
        url_path="solicitar-delivery",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def solicitar_delivery(self, request, pk=None):
        """Asigna un envío en vivo con proveedor de delivery externo a la ruta."""
        ruta = self.get_object()
        ser = SolicitarDeliveryRutaInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            res = solicitar_delivery_externo_ruta(
                ruta,
                proveedor_codigo=vd["proveedor"],
                destino_lat=vd["destino_lat"],
                destino_lng=vd["destino_lng"],
                direccion_destino=vd["direccion_destino"],
            )
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(res, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="tracking-delivery")
    def tracking_delivery(self, request, pk=None):
        """Consulta el estado del tracking en el proveedor de delivery externo."""
        ruta = self.get_object()
        try:
            res = consultar_tracking_delivery_ruta(ruta)
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(res, status=status.HTTP_200_OK)

    @swagger_auto_schema(request_body=EmitirGuiaSeniatInputSerializer)
    @idempotent(scope="despacho:emitir_guia_seniat")
    @action(
        detail=True,
        methods=["post"],
        url_path="emitir-guia-seniat",
        throttle_classes=[*viewsets.ModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def emitir_guia_seniat(self, request, pk=None):
        """Emite Guía de Despacho Digital SENIAT desde la ruta vía Imprenta Digital."""
        ruta = self.get_object()
        ser = EmitirGuiaSeniatInputSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        try:
            res = emitir_guia_despacho_seniat(ruta, proveedor=ser.validated_data["proveedor"])
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(res, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="torre-control")
    def torre_control(self, request):
        """Snapshot de torre de control logística en vivo para mapa GPS y KPIs."""
        empresa = _resolver_empresa(request)
        return Response(torre_control_tms(empresa), status=status.HTTP_200_OK)


class ParadaEntregaViewSet(TenantFKScopeMixin, NulSafeFilterMixin, ActiveFilterMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ParadaEntrega.objects.all()
    serializer_class = ParadaEntregaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["id_despacho__numero_despacho", "direccion_texto", "epod_receptor_nombre"]
    ordering_fields = ["secuencia", "estado", "eta_estimada", "fecha_creacion"]
    ordering = ["secuencia"]

    def get_queryset(self):
        qs = ParadaEntrega.objects.filter(id_empresa__in=get_empresas_visible(self.request.user)).select_related(
            "id_ruta", "id_despacho"
        )
        ruta_id = self.request.query_params.get("ruta")
        if ruta_id:
            qs = qs.filter(id_ruta_id=validar_uuid_param(ruta_id, "ruta"))
        return qs

    @swagger_auto_schema(request_body=RegistrarEPODInputSerializer)
    @idempotent(scope="despacho:registrar_epod")
    @action(
        detail=True,
        methods=["post"],
        url_path="registrar-epod",
        throttle_classes=[*viewsets.ReadOnlyModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def registrar_epod(self, request, pk=None):
        """Registra Prueba de Entrega Digital (foto, firma, GPS) y cobro contra entrega."""
        parada = self.get_object()
        ser = RegistrarEPODInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            res = registrar_epod_parada(
                parada,
                request.user,
                resultado=vd["resultado"],
                receptor_nombre=vd["receptor_nombre"],
                receptor_cedula=vd["receptor_cedula"],
                firma_base64=vd["firma_base64"],
                foto_url=vd["foto_url"],
                latitud=vd.get("latitud"),
                longitud=vd.get("longitud"),
                observaciones=vd["observaciones"],
                motivo_rechazo=vd["motivo_rechazo"],
                cobro=vd.get("cobro"),
            )
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        parada.refresh_from_db()
        return Response(
            {
                "parada": ParadaEntregaSerializer(parada, context={"request": request}).data,
                "despacho_estado": res["despacho_estado"],
                "pago_id": res["pago_id"],
                "ruta_completada": res["ruta_completada"],
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="whatsapp-tracking")
    def whatsapp_tracking(self, request, pk=None):
        """Genera el enlace público de tracking y deeplink listo para WhatsApp."""
        parada = self.get_object()
        base_url = _no_nul(request.query_params.get("base_url"), "base_url") or ""
        return Response(generar_payload_tracking_whatsapp(parada, base_url=base_url), status=status.HTTP_200_OK)


class TrackingPublicoParadaView(APIView):
    """Endpoint público mínimo (sin PII sensible) para tracking del cliente vía token UUID."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request, token):
        uid = validar_uuid_param(str(token), "token")
        parada = (
            ParadaEntrega.objects.select_related("id_ruta", "id_ruta__id_vehiculo", "id_despacho")
            .filter(token_tracking=uid, activo=True)
            .first()
        )
        if parada is None:
            return Response({"detail": "Tracking no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        veh = parada.id_ruta.id_vehiculo
        return Response(
            {
                "numero_despacho": parada.id_despacho.numero_despacho,
                "ruta_codigo": parada.id_ruta.codigo,
                "secuencia": parada.secuencia,
                "estado": parada.estado,
                "estado_display": parada.get_estado_display(),
                "eta_estimada": parada.eta_estimada.isoformat() if parada.eta_estimada else None,
                "fecha_llegada_real": parada.fecha_llegada_real.isoformat() if parada.fecha_llegada_real else None,
                "vehiculo_lat": str(veh.latitud_actual) if veh and veh.latitud_actual is not None else None,
                "vehiculo_lng": str(veh.longitud_actual) if veh and veh.longitud_actual is not None else None,
                "proveedor_delivery_externo": parada.id_ruta.proveedor_delivery_externo,
                "tracking_url_externo": parada.id_ruta.tracking_url_externo,
            },
            status=status.HTTP_200_OK,
        )
