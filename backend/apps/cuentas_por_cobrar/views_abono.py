from rest_framework import viewsets
from .models import AbonoCxC
from .serializers_abono import AbonoCxCSerializer
from apps.core.viewsets import BaseModelViewSet

class AbonoCxCViewSet(BaseModelViewSet):
    queryset = AbonoCxC.objects.all()
    serializer_class = AbonoCxCSerializer
