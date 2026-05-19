from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import (
    CentroTrabajo,
    ConsumoMaterial,
    ListaMateriales,
    ListaMaterialesDetalle,
    OperacionProduccion,
    OrdenProduccion,
    ProduccionTerminada,
    RegistroOperacion,
    RutaProduccion,
    RutaProduccionDetalle,
)
from .serializers import (
    CentroTrabajoSerializer,
    ConsumoMaterialSerializer,
    ListaMaterialesDetalleSerializer,
    ListaMaterialesSerializer,
    OperacionProduccionSerializer,
    OrdenProduccionSerializer,
    ProduccionTerminadaSerializer,
    RegistroOperacionSerializer,
    RutaProduccionDetalleSerializer,
    RutaProduccionSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class ListaMaterialesViewSet(BaseModelViewSet):
    queryset = ListaMateriales.objects.all()
    serializer_class = ListaMaterialesSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return ListaMateriales.objects.filter(empresa__in=_empresas(self.request))


class RutaProduccionViewSet(BaseModelViewSet):
    queryset = RutaProduccion.objects.all()
    serializer_class = RutaProduccionSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return RutaProduccion.objects.filter(empresa__in=_empresas(self.request))


class OrdenProduccionViewSet(BaseModelViewSet):
    queryset = OrdenProduccion.objects.all()
    serializer_class = OrdenProduccionSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return OrdenProduccion.objects.filter(empresa__in=_empresas(self.request))


class ConsumoMaterialViewSet(BaseModelViewSet):
    queryset = ConsumoMaterial.objects.all()
    serializer_class = ConsumoMaterialSerializer

    def get_queryset(self):
        # R-CODE-1 — ConsumoMaterial llega via orden_produccion→OrdenProduccion
        return ConsumoMaterial.objects.filter(orden_produccion__empresa__in=_empresas(self.request))


class ProduccionTerminadaViewSet(BaseModelViewSet):
    queryset = ProduccionTerminada.objects.all()
    serializer_class = ProduccionTerminadaSerializer

    def get_queryset(self):
        # R-CODE-1 — ProduccionTerminada llega via orden_produccion→OrdenProduccion
        return ProduccionTerminada.objects.filter(orden_produccion__empresa__in=_empresas(self.request))


class ListaMaterialesDetalleViewSet(BaseModelViewSet):
    queryset = ListaMaterialesDetalle.objects.all()
    serializer_class = ListaMaterialesDetalleSerializer

    def get_queryset(self):
        # R-CODE-1 — ListaMaterialesDetalle llega via id_lista_materiales→ListaMateriales
        return ListaMaterialesDetalle.objects.filter(id_lista_materiales__empresa__in=_empresas(self.request))


class CentroTrabajoViewSet(BaseModelViewSet):
    queryset = CentroTrabajo.objects.all()
    serializer_class = CentroTrabajoSerializer

    def get_queryset(self):
        # R-CODE-1
        return CentroTrabajo.objects.filter(id_empresa__in=_empresas(self.request))


class OperacionProduccionViewSet(BaseModelViewSet):
    queryset = OperacionProduccion.objects.all()
    serializer_class = OperacionProduccionSerializer

    def get_queryset(self):
        # R-CODE-1
        return OperacionProduccion.objects.filter(id_empresa__in=_empresas(self.request))


class RutaProduccionDetalleViewSet(BaseModelViewSet):
    queryset = RutaProduccionDetalle.objects.all()
    serializer_class = RutaProduccionDetalleSerializer

    def get_queryset(self):
        # R-CODE-1 — RutaProduccionDetalle llega via id_ruta_produccion→RutaProduccion
        return RutaProduccionDetalle.objects.filter(id_ruta_produccion__empresa__in=_empresas(self.request))


class RegistroOperacionViewSet(BaseModelViewSet):
    queryset = RegistroOperacion.objects.all()
    serializer_class = RegistroOperacionSerializer

    def get_queryset(self):
        # R-CODE-1 — RegistroOperacion llega via id_orden_produccion→OrdenProduccion
        return RegistroOperacion.objects.filter(id_orden_produccion__empresa__in=_empresas(self.request))
