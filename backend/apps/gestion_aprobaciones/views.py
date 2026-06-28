from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion, TipoAprobacion
from .serializers import (
    FlujoAprobacionSerializer,
    RegistroAprobacionSerializer,
    SolicitudAprobacionSerializer,
    TipoAprobacionSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class TipoAprobacionViewSet(BaseModelViewSet):
    queryset = TipoAprobacion.objects.all()
    serializer_class = TipoAprobacionSerializer

    def get_queryset(self):
        # R-CODE-1
        return TipoAprobacion.objects.filter(id_empresa__in=_empresas(self.request))


class FlujoAprobacionViewSet(BaseModelViewSet):
    queryset = FlujoAprobacion.objects.all()
    serializer_class = FlujoAprobacionSerializer

    def get_queryset(self):
        # R-CODE-1 — FlujoAprobacion no tiene id_empresa directo; llega via id_tipo_aprobacion→TipoAprobacion
        return FlujoAprobacion.objects.filter(id_tipo_aprobacion__id_empresa__in=_empresas(self.request))


class SolicitudAprobacionViewSet(BaseModelViewSet):
    queryset = SolicitudAprobacion.objects.all()
    serializer_class = SolicitudAprobacionSerializer

    def get_queryset(self):
        # R-CODE-1 — SolicitudAprobacion llega via id_tipo_aprobacion→TipoAprobacion
        return SolicitudAprobacion.objects.filter(id_tipo_aprobacion__id_empresa__in=_empresas(self.request))

    def create(self, request, *args, **kwargs):
        # Las solicitudes las crea el servicio (crear_solicitud) desde el flujo de
        # aprobación de compras/gastos, nunca por POST directo: así no se pueden
        # fabricar solicitudes apuntando a documentos arbitrarios (SEC LOW-5).
        return Response(
            {"detail": "Las solicitudes se crean desde el flujo de aprobación, no por POST directo."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["post"])
    def decidir(self, request, pk=None):
        """Registra una decisión (aprobar/rechazar) sobre la etapa actual.

        Body: {"aprobado": true|false, "comentarios": "..."}. El avance entre
        etapas y el cierre (APROBADA/RECHAZADA) lo maneja el servicio atómico.
        """
        from .services import AprobacionError, registrar_decision

        solicitud = self.get_object()  # acotado por tenant vía get_queryset
        aprobado = request.data.get("aprobado")
        if aprobado is None:
            return Response(
                {"error": "El campo 'aprobado' (true/false) es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        comentarios = request.data.get("comentarios", "")
        try:
            registrar_decision(solicitud, request.user, bool(aprobado), comentarios)
        except AprobacionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        solicitud.refresh_from_db()
        return Response(self.get_serializer(solicitud).data)


class RegistroAprobacionViewSet(BaseModelViewSet):
    queryset = RegistroAprobacion.objects.all()
    serializer_class = RegistroAprobacionSerializer

    def get_queryset(self):
        # R-CODE-1 — RegistroAprobacion llega via id_solicitud_aprobacion→SolicitudAprobacion→id_tipo_aprobacion
        return RegistroAprobacion.objects.filter(
            id_solicitud_aprobacion__id_tipo_aprobacion__id_empresa__in=_empresas(self.request)
        )
