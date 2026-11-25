from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import (
    BaseModelViewSet,
    SuperuserWriteMixin,
    get_empresa_primaria,
    get_empresas_visible,
    validar_uuid_param,
)

from .migrador_1click import (
    MigracionError,
    ejecutar_migracion_1click,
    listar_formatos_migracion,
    preview_migracion_1click,
)
from .models import DetalleErrorMigracion, PlantillaMigracion, ProcesoMigracion
from .serializers import (
    DetalleErrorMigracionSerializer,
    Migrador1ClickEjecutarResponseSerializer,
    Migrador1ClickFormatosResponseSerializer,
    Migrador1ClickInputSerializer,
    Migrador1ClickPreviewInputSerializer,
    Migrador1ClickPreviewResponseSerializer,
    PlantillaMigracionSerializer,
    ProcesoMigracionSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class PlantillaMigracionViewSet(SuperuserWriteMixin, BaseModelViewSet):
    """Plantillas de migración globales. Escritura solo superusuario (H-SEC-6)."""

    queryset = PlantillaMigracion.objects.all()
    serializer_class = PlantillaMigracionSerializer

    def get_queryset(self):
        # Catálogo global (sin id_empresa); FK por empresa queda para Fase 2.
        return PlantillaMigracion.objects.all()


class ProcesoMigracionViewSet(BaseModelViewSet):
    queryset = ProcesoMigracion.objects.all()
    serializer_class = ProcesoMigracionSerializer

    def get_queryset(self):
        # R-CODE-1
        return ProcesoMigracion.objects.filter(id_empresa__in=_empresas(self.request))


class DetalleErrorMigracionViewSet(BaseModelViewSet):
    queryset = DetalleErrorMigracion.objects.all()
    serializer_class = DetalleErrorMigracionSerializer

    def get_queryset(self):
        # R-CODE-1 — DetalleErrorMigracion llega via id_proceso_migracion→ProcesoMigracion
        return DetalleErrorMigracion.objects.filter(id_proceso_migracion__id_empresa__in=_empresas(self.request))


def _resolver_empresa_migracion(request, id_empresa=None):
    visibles = get_empresas_visible(request.user)
    raw_emp = (
        id_empresa
        or request.query_params.get("id_empresa")
        or request.headers.get("X-Empresa-ID")
    )
    if raw_emp:
        uid = validar_uuid_param(str(raw_emp), "id_empresa")
        emp = visibles.filter(pk=uid).first()
        if emp is None:
            raise PermissionDenied("Empresa fuera del alcance del usuario autenticado.")
        return emp
    emp = get_empresa_primaria(request.user) or visibles.first()
    if emp is None:
        raise ValidationError({"id_empresa": "Usuario sin empresa asignada."})
    return emp


class Migrador1ClickViewSet(viewsets.ViewSet):
    """Migrador 1-Click desde Odoo (SOLO LECTURA) y CSV VE Saint/Profit/Galac (Plan 09 Fase 8.4)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle]

    @swagger_auto_schema(responses={200: Migrador1ClickFormatosResponseSerializer})
    @action(detail=False, methods=["get"], url_path="formatos")
    def formatos(self, request):
        return Response(listar_formatos_migracion())

    @swagger_auto_schema(
        request_body=Migrador1ClickPreviewInputSerializer,
        responses={200: Migrador1ClickPreviewResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request):
        ser = Migrador1ClickPreviewInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        empresa = _resolver_empresa_migracion(request, vd.get("id_empresa"))
        try:
            resultado = preview_migracion_1click(
                empresa,
                fuente=vd["fuente"],
                entidad=vd["entidad"],
                contenido_csv=vd.get("contenido_csv"),
                id_conector=vd.get("id_conector"),
                limite=vd.get("limite", 500),
                muestra=vd.get("muestra", 10),
            )
        except MigracionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(resultado, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        request_body=Migrador1ClickInputSerializer,
        responses={201: Migrador1ClickEjecutarResponseSerializer},
    )
    @idempotent(scope="migracion_datos:ejecutar_1click")
    @action(detail=False, methods=["post"], url_path="ejecutar")
    def ejecutar(self, request):
        ser = Migrador1ClickInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        empresa = _resolver_empresa_migracion(request, vd.get("id_empresa"))
        try:
            resultado = ejecutar_migracion_1click(
                empresa,
                request.user,
                fuente=vd["fuente"],
                entidad=vd["entidad"],
                contenido_csv=vd.get("contenido_csv"),
                id_conector=vd.get("id_conector"),
                limite=vd.get("limite", 500),
            )
        except MigracionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(resultado, status=status.HTTP_201_CREATED)
