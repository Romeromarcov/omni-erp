from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Caja, MovimientoInternoFondo, OperacionCambioDivisa
from .serializers import CajaSerializer, MovimientoInternoFondoSerializer, OperacionCambioDivisaSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class CajaViewSet(BaseModelViewSet):
    queryset = Caja.objects.all()
    serializer_class = CajaSerializer

    def get_queryset(self):
        # R-CODE-1 — Caja (finanzas) usa "empresa" como FK (no "id_empresa")
        return Caja.objects.filter(empresa__in=_empresas(self.request))


class MovimientoInternoFondoViewSet(BaseModelViewSet):
    queryset = MovimientoInternoFondo.objects.all()
    serializer_class = MovimientoInternoFondoSerializer

    def get_queryset(self):
        # R-CODE-1 — MovimientoInternoFondo no tiene id_empresa directo; llega via caja_origen→Caja
        return MovimientoInternoFondo.objects.filter(caja_origen__empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        serializer.save()


class OperacionCambioDivisaViewSet(BaseModelViewSet):
    queryset = OperacionCambioDivisa.objects.all()
    serializer_class = OperacionCambioDivisaSerializer

    def get_queryset(self):
        # R-CODE-1 — el campo FK a empresa es "empresa" (no "id_empresa")
        return OperacionCambioDivisa.objects.filter(empresa__in=_empresas(self.request))

    def perform_create(self, serializer):
        serializer.save()
