from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

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


class ListaMaterialesViewSet(BaseModelViewSet):
    queryset = ListaMateriales.objects.all()
    serializer_class = ListaMaterialesSerializer


class RutaProduccionViewSet(BaseModelViewSet):
    queryset = RutaProduccion.objects.all()
    serializer_class = RutaProduccionSerializer


class OrdenProduccionViewSet(BaseModelViewSet):
    queryset = OrdenProduccion.objects.all()
    serializer_class = OrdenProduccionSerializer


class ConsumoMaterialViewSet(BaseModelViewSet):
    queryset = ConsumoMaterial.objects.all()
    serializer_class = ConsumoMaterialSerializer


class ProduccionTerminadaViewSet(BaseModelViewSet):
    queryset = ProduccionTerminada.objects.all()
    serializer_class = ProduccionTerminadaSerializer


class ListaMaterialesDetalleViewSet(BaseModelViewSet):
    queryset = ListaMaterialesDetalle.objects.all()
    serializer_class = ListaMaterialesDetalleSerializer


class CentroTrabajoViewSet(BaseModelViewSet):
    queryset = CentroTrabajo.objects.all()
    serializer_class = CentroTrabajoSerializer


class OperacionProduccionViewSet(BaseModelViewSet):
    queryset = OperacionProduccion.objects.all()
    serializer_class = OperacionProduccionSerializer


class RutaProduccionDetalleViewSet(BaseModelViewSet):
    queryset = RutaProduccionDetalle.objects.all()
    serializer_class = RutaProduccionDetalleSerializer


class RegistroOperacionViewSet(BaseModelViewSet):
    queryset = RegistroOperacion.objects.all()
    serializer_class = RegistroOperacionSerializer
