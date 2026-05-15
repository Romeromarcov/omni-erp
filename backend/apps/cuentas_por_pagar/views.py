from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import CuentaPorPagar
from .serializers import CuentaPorPagarSerializer


class CuentaPorPagarViewSet(BaseModelViewSet):
    queryset = CuentaPorPagar.objects.all()
    serializer_class = CuentaPorPagarSerializer
