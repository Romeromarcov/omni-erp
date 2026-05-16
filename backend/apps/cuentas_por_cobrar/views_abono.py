from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import AbonoCxC
from .serializers_abono import AbonoCxCSerializer


class AbonoCxCViewSet(BaseModelViewSet):
    queryset = AbonoCxC.objects.all()
    serializer_class = AbonoCxCSerializer

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        return AbonoCxC.objects.filter(
            cuenta_por_cobrar__empresa__in=empresas
        ).select_related("cuenta_por_cobrar", "usuario")
