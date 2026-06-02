from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, SuperuserWriteMixin, get_empresas_visible

from .models import DetalleErrorMigracion, PlantillaMigracion, ProcesoMigracion
from .serializers import DetalleErrorMigracionSerializer, PlantillaMigracionSerializer, ProcesoMigracionSerializer


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
