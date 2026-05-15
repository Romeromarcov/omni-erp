from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import AbonoCxC
from .serializers_abono import AbonoCxCSerializer


class AbonoCxCViewSet(BaseModelViewSet):
    queryset = AbonoCxC.objects.all()
    serializer_class = AbonoCxCSerializer
