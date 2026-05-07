from rest_framework import viewsets
from .models import LogAuditoria
from .serializers import LogAuditoriaSerializer

class LogAuditoriaViewSet(viewsets.ModelViewSet):
    queryset = LogAuditoria.objects.all()
    serializer_class = LogAuditoriaSerializer
