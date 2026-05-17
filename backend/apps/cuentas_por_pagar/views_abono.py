from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import AbonoCxP
from .serializers_abono import AbonoCxPSerializer


class AbonoCxPViewSet(BaseModelViewSet):
    queryset = AbonoCxP.objects.all()
    serializer_class = AbonoCxPSerializer

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        return AbonoCxP.objects.filter(
            cuenta_por_pagar__id_empresa__in=empresas
        ).select_related("cuenta_por_pagar", "usuario")
