"""ViewSets de la configuración del motor CxC Lubrikca (Fase 1).

Un ViewSet por modelo, heredando ``SoftDeleteModelMixin`` (DELETE → soft delete
vía ``deleted_at``) y ``BaseModelViewSet`` (auth, paginación, búsqueda, scope de
FKs tenant-aware). Cada ViewSet:

- acota su queryset a empresas visibles del usuario y excluye soft-deleted;
- fuerza ``empresa`` en la creación (multi-tenant R-CODE-1, H-API-1);
- sobreescribe ``search_fields`` / ``ordering_fields`` a campos reales del modelo
  (el default de ``BaseModelViewSet`` referencia campos de ``Empresa``).
"""

from __future__ import annotations

from apps.core.viewsets import (
    BaseModelViewSet,
    SoftDeleteModelMixin,
    get_empresas_visible,
)
from apps.cxc_lubrikca.models import (
    DescuentoBCVCompleto,
    DescuentoMarcaCategoria,
    Feriado,
    MetodoPago,
    PromocionPrimeraCompra,
    ReglaRecurrencia,
)

from .serializers import (
    DescuentoBCVCompletoSerializer,
    DescuentoMarcaCategoriaSerializer,
    FeriadoSerializer,
    MetodoPagoSerializer,
    PromocionPrimeraCompraSerializer,
    ReglaRecurrenciaSerializer,
)


class _CxcLubrikcaConfigViewSet(SoftDeleteModelMixin, BaseModelViewSet):
    """Base común: scope multi-tenant + exclusión de soft-deleted + inyección de empresa."""

    model = None  # subclases lo fijan

    def get_queryset(self):
        return self.model.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        )

    def perform_create(self, serializer):
        empresa = get_empresas_visible(self.request.user).first()
        if empresa is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("El usuario no tiene una empresa asignada.")
        serializer.save(empresa=empresa)


class DescuentoMarcaCategoriaViewSet(_CxcLubrikcaConfigViewSet):
    model = DescuentoMarcaCategoria
    queryset = DescuentoMarcaCategoria.objects.all()
    serializer_class = DescuentoMarcaCategoriaSerializer
    search_fields = ["marca", "categoria"]
    ordering_fields = ["vigencia_desde", "vigencia_hasta", "porcentaje", "marca", "categoria"]


class DescuentoBCVCompletoViewSet(_CxcLubrikcaConfigViewSet):
    model = DescuentoBCVCompleto
    queryset = DescuentoBCVCompleto.objects.all()
    serializer_class = DescuentoBCVCompletoSerializer
    search_fields = []
    ordering_fields = ["vigencia_desde", "vigencia_hasta", "porcentaje"]


class PromocionPrimeraCompraViewSet(_CxcLubrikcaConfigViewSet):
    model = PromocionPrimeraCompra
    queryset = PromocionPrimeraCompra.objects.all()
    serializer_class = PromocionPrimeraCompraSerializer
    search_fields = ["producto"]
    ordering_fields = ["vigencia_desde", "vigencia_hasta", "producto"]


class ReglaRecurrenciaViewSet(_CxcLubrikcaConfigViewSet):
    model = ReglaRecurrencia
    queryset = ReglaRecurrencia.objects.all()
    serializer_class = ReglaRecurrenciaSerializer
    search_fields = ["condicion", "tipo_beneficio"]
    ordering_fields = ["vigencia_desde", "vigencia_hasta", "valor", "condicion"]


class FeriadoViewSet(_CxcLubrikcaConfigViewSet):
    model = Feriado
    queryset = Feriado.objects.all()
    serializer_class = FeriadoSerializer
    search_fields = ["descripcion"]
    ordering_fields = ["fecha", "descripcion", "tipo"]


class MetodoPagoViewSet(_CxcLubrikcaConfigViewSet):
    model = MetodoPago
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    search_fields = ["nombre", "codigo"]
    ordering_fields = ["nombre", "codigo", "moneda"]
