import uuid

from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion, TipoAprobacion
from .serializers import (
    DecidirSolicitudInputSerializer,
    FlujoAprobacionSerializer,
    RegistroAprobacionSerializer,
    SolicitudAprobacionSerializer,
    TipoAprobacionSerializer,
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


class TipoAprobacionViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = TipoAprobacion.objects.all()
    serializer_class = TipoAprobacionSerializer
    search_fields = ["codigo_tipo", "nombre_tipo", "modulo_origen"]
    ordering_fields = ["codigo_tipo", "nombre_tipo", "modulo_origen", "activo"]

    def get_queryset(self):
        # R-CODE-1
        qs = TipoAprobacion.objects.filter(id_empresa__in=_empresas(self.request))
        empresa_id = self.request.query_params.get("id_empresa")
        modulo = self.request.query_params.get("modulo_origen")
        if empresa_id:
            qs = qs.filter(id_empresa_id=_validar_uuid(empresa_id, "id_empresa"))
        if modulo:
            qs = qs.filter(modulo_origen=modulo.replace("\x00", "").strip())
        return qs


class FlujoAprobacionViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = FlujoAprobacion.objects.all()
    serializer_class = FlujoAprobacionSerializer
    search_fields = ["nombre_etapa"]
    ordering_fields = ["orden_etapa", "nombre_etapa", "monto_minimo", "monto_maximo", "sla_horas", "activo"]

    def get_queryset(self):
        # R-CODE-1 — FlujoAprobacion no tiene id_empresa directo; llega via id_tipo_aprobacion→TipoAprobacion
        qs = FlujoAprobacion.objects.filter(id_tipo_aprobacion__id_empresa__in=_empresas(self.request))
        tipo_id = self.request.query_params.get("id_tipo_aprobacion")
        dep_id = self.request.query_params.get("id_departamento")
        if tipo_id:
            qs = qs.filter(id_tipo_aprobacion_id=_validar_uuid(tipo_id, "id_tipo_aprobacion"))
        if dep_id:
            qs = qs.filter(id_departamento_id=_validar_uuid(dep_id, "id_departamento"))
        return qs


class SolicitudAprobacionViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = SolicitudAprobacion.objects.all()
    serializer_class = SolicitudAprobacionSerializer
    search_fields = ["nombre_modelo_origen", "estado_solicitud", "comentarios_solicitante"]
    ordering_fields = [
        "fecha_solicitud",
        "fecha_ultima_actualizacion",
        "estado_solicitud",
        "monto",
        "fecha_inicio_etapa",
        "escalada",
    ]

    def get_queryset(self):
        # R-CODE-1 — SolicitudAprobacion llega via id_tipo_aprobacion→TipoAprobacion
        qs = SolicitudAprobacion.objects.filter(id_tipo_aprobacion__id_empresa__in=_empresas(self.request))
        tipo_id = self.request.query_params.get("id_tipo_aprobacion")
        estado = self.request.query_params.get("estado_solicitud")
        escalada = self.request.query_params.get("escalada")
        if tipo_id:
            qs = qs.filter(id_tipo_aprobacion_id=_validar_uuid(tipo_id, "id_tipo_aprobacion"))
        if estado:
            qs = qs.filter(estado_solicitud=estado.replace("\x00", "").strip())
        if escalada is not None and escalada != "":
            qs = qs.filter(escalada=escalada.replace("\x00", "").strip().lower() in ("true", "1", "yes"))
        return qs

    def create(self, request, *args, **kwargs):
        # Las solicitudes las crea el servicio (crear_solicitud) desde el flujo de
        # aprobación de compras/gastos, nunca por POST directo: así no se pueden
        # fabricar solicitudes apuntando a documentos arbitrarios (SEC LOW-5).
        return Response(
            {"detail": "Las solicitudes se crean desde el flujo de aprobación, no por POST directo."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @swagger_auto_schema(
        request_body=DecidirSolicitudInputSerializer,
        responses={200: SolicitudAprobacionSerializer},
    )
    @action(detail=True, methods=["post"])
    def decidir(self, request, pk=None):
        """Registra una decisión (aprobar/rechazar) sobre la etapa actual.

        Body: {"aprobado": true|false, "comentarios": "..."}. El avance entre
        etapas y el cierre (APROBADA/RECHAZADA) lo maneja el servicio atómico.
        """
        from .services import AprobacionError, registrar_decision

        solicitud = self.get_object()  # acotado por tenant vía get_queryset
        aprobado_raw = request.data.get("aprobado")
        if aprobado_raw is None:
            return Response(
                {"error": "El campo 'aprobado' (true/false) es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            aprobado = drf_serializers.BooleanField().to_internal_value(aprobado_raw)
        except ValidationError:
            return Response(
                {"error": "El campo 'aprobado' debe ser booleano (true/false)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comentarios_raw = request.data.get("comentarios", "")
        comentarios = "" if comentarios_raw is None else str(comentarios_raw)
        try:
            registrar_decision(solicitud, request.user, aprobado, comentarios)
        except AprobacionError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        solicitud.refresh_from_db()
        return Response(self.get_serializer(solicitud).data)


class RegistroAprobacionViewSet(_NulSafeFilterMixin, BaseModelViewSet):
    queryset = RegistroAprobacion.objects.all()
    serializer_class = RegistroAprobacionSerializer
    search_fields = ["tipo_decision", "comentarios"]
    ordering_fields = ["fecha_decision", "tipo_decision"]

    def get_queryset(self):
        # R-CODE-1 — RegistroAprobacion llega via id_solicitud_aprobacion→SolicitudAprobacion→id_tipo_aprobacion
        qs = RegistroAprobacion.objects.filter(
            id_solicitud_aprobacion__id_tipo_aprobacion__id_empresa__in=_empresas(self.request)
        )
        sol_id = self.request.query_params.get("id_solicitud_aprobacion")
        if sol_id:
            qs = qs.filter(id_solicitud_aprobacion_id=_validar_uuid(sol_id, "id_solicitud_aprobacion"))
        return qs
