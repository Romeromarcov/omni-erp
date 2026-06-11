from rest_framework import viewsets
from apps.core.serializer_mixins import TenantFKScopeMixin
from rest_framework.permissions import IsAuthenticated

from apps.core.viewsets import get_empresas_visible

from .models import LogAuditoria
from .serializers import LogAuditoriaSerializer


class LogAuditoriaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = LogAuditoria.objects.all()
    serializer_class = LogAuditoriaSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]  # Logs son solo lectura

    def get_queryset(self):
        # R-CODE-1 — logs de auditoría solo visibles dentro de la propia empresa
        empresas = get_empresas_visible(self.request.user)
        return LogAuditoria.objects.filter(id_empresa__in=empresas).order_by("-fecha_hora_accion")
