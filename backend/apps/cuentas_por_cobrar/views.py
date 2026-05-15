from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import CuentaPorCobrar
from .serializers import CuentaPorCobrarSerializer


class CuentaPorCobrarViewSet(BaseModelViewSet):
    queryset = CuentaPorCobrar.objects.all()
    serializer_class = CuentaPorCobrarSerializer
