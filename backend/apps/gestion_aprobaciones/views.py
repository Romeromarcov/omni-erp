from rest_framework import viewsets

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


class RegistroAprobacionViewSet(BaseModelViewSet):
    queryset = RegistroAprobacion.objects.all()
    serializer_class = RegistroAprobacionSerializer

    def get_queryset(self):
        # R-CODE-1 — RegistroAprobacion llega via id_solicitud_aprobacion→SolicitudAprobacion→id_tipo_aprobacion
        return RegistroAprobacion.objects.filter(
            id_solicitud_aprobacion__id_tipo_aprobacion__id_empresa__in=_empresas(self.request)
        )
