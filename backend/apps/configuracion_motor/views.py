from apps.core.viewsets import BaseModelViewSet, SuperuserWriteMixin, get_empresas_visible

from .models import CatalogoValor, ParametroSistema, TipoDocumento
from .serializers import CatalogoValorSerializer, ParametroSistemaSerializer, TipoDocumentoSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class TipoDocumentoViewSet(SuperuserWriteMixin, BaseModelViewSet):
    """Catálogo global de tipos de documento. Lectura: cualquiera; escritura: superusuario (H-SEC-6)."""

    queryset = TipoDocumento.objects.all()
    serializer_class = TipoDocumentoSerializer

    def get_queryset(self):
        # Catálogo global (sin id_empresa); la FK por empresa queda para Fase 2.
        return TipoDocumento.objects.all()


class ParametroSistemaViewSet(SuperuserWriteMixin, BaseModelViewSet):
    """
    Parámetros del sistema. id_empresa nullable: las filas de empresa las
    gestiona el tenant; las globales (id_empresa=None) solo el superusuario
    (H-SEC-6 / cierra S-13).
    """

    queryset = ParametroSistema.objects.all()
    serializer_class = ParametroSistemaSerializer

    def get_queryset(self):
        # Filas de empresas visibles + globales (id_empresa=None).
        return ParametroSistema.objects.filter(id_empresa__in=_empresas(self.request)) | ParametroSistema.objects.filter(
            id_empresa__isnull=True
        )

    def _es_fila_global(self, instance_or_data) -> bool:
        # Solo es "global" (gate superusuario) si no hay empresa asociada.
        if hasattr(instance_or_data, "id_empresa"):
            return instance_or_data.id_empresa_id is None
        return instance_or_data.get("id_empresa") is None


class CatalogoValorViewSet(SuperuserWriteMixin, BaseModelViewSet):
    """Catálogo global de valores. Lectura: cualquiera; escritura: superusuario (H-SEC-6)."""

    queryset = CatalogoValor.objects.all()
    serializer_class = CatalogoValorSerializer

    def get_queryset(self):
        # Catálogo global (sin id_empresa); la FK por empresa queda para Fase 2.
        return CatalogoValor.objects.all()
