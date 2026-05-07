from rest_framework import viewsets
from .models import CuentaPorCobrar
from .serializers import CuentaPorCobrarSerializer
from apps.core.viewsets import BaseModelViewSet

class CuentaPorCobrarViewSet(BaseModelViewSet):
    queryset = CuentaPorCobrar.objects.all()
    serializer_class = CuentaPorCobrarSerializer
