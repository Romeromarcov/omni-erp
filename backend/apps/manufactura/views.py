from rest_framework import viewsets
from .models import (
    ListaMateriales, RutaProduccion, OrdenProduccion, ConsumoMaterial,
    ProduccionTerminada, ListaMaterialesDetalle, CentroTrabajo,
    OperacionProduccion, RutaProduccionDetalle, RegistroOperacion
)
from .serializers import (
    ListaMaterialesSerializer, RutaProduccionSerializer, OrdenProduccionSerializer,
    ConsumoMaterialSerializer, ProduccionTerminadaSerializer,
    ListaMaterialesDetalleSerializer, CentroTrabajoSerializer,
    OperacionProduccionSerializer, RutaProduccionDetalleSerializer,
    RegistroOperacionSerializer
)
from apps.core.viewsets import BaseModelViewSet

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
