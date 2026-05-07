
from rest_framework import viewsets
from .models import CuentaPorPagar
from .serializers import CuentaPorPagarSerializer
from apps.core.viewsets import BaseModelViewSet

class CuentaPorPagarViewSet(BaseModelViewSet):
    queryset = CuentaPorPagar.objects.all()
    serializer_class = CuentaPorPagarSerializer
