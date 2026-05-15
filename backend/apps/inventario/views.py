from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import (
    CategoriaProducto,
    ConversionUnidadMedida,
    MovimientoInventario,
    Producto,
    StockActual,
    StockConsignacionCliente,
    StockConsignacionProveedor,
    UnidadMedida,
    VarianteProducto,
)
from .serializers import (
    CategoriaProductoSerializer,
    ConversionUnidadMedidaSerializer,
    MovimientoInventarioSerializer,
    ProductoSerializer,
    StockActualSerializer,
    StockConsignacionClienteSerializer,
    StockConsignacionProveedorSerializer,
    UnidadMedidaSerializer,
    VarianteProductoSerializer,
)


def _empresas(request):
    """Helper: devuelve el queryset de empresas visibles para el usuario."""
    return get_empresas_visible(request.user)


class UnidadMedidaViewSet(BaseModelViewSet):
    queryset = UnidadMedida.objects.all()
    serializer_class = UnidadMedidaSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario
        return UnidadMedida.objects.filter(id_empresa__in=_empresas(self.request))


class CategoriaProductoViewSet(BaseModelViewSet):
    queryset = CategoriaProducto.objects.all()
    serializer_class = CategoriaProductoSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario
        return CategoriaProducto.objects.filter(id_empresa__in=_empresas(self.request)).order_by("nombre_categoria")


class ProductoViewSet(BaseModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar SIEMPRE por empresas visibles; el parámetro
        # ?empresa= es opcional para restringir aún más dentro de las propias.
        qs = Producto.objects.filter(id_empresa__in=_empresas(self.request))
        empresa_id = self.request.query_params.get("empresa")
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        return qs


class VarianteProductoViewSet(BaseModelViewSet):
    queryset = VarianteProducto.objects.all()
    serializer_class = VarianteProductoSerializer


class StockActualViewSet(BaseModelViewSet):
    queryset = StockActual.objects.all()
    serializer_class = StockActualSerializer

    def get_queryset(self):
        # R-CODE-1
        return StockActual.objects.filter(id_empresa__in=_empresas(self.request))


class MovimientoInventarioViewSet(BaseModelViewSet):
    queryset = MovimientoInventario.objects.all()
    serializer_class = MovimientoInventarioSerializer

    def get_queryset(self):
        # R-CODE-1
        return MovimientoInventario.objects.filter(id_empresa__in=_empresas(self.request))


class ConversionUnidadMedidaViewSet(BaseModelViewSet):
    queryset = ConversionUnidadMedida.objects.all()
    serializer_class = ConversionUnidadMedidaSerializer

    def get_queryset(self):
        # R-CODE-1
        return ConversionUnidadMedida.objects.filter(id_empresa__in=_empresas(self.request))


class StockConsignacionClienteViewSet(BaseModelViewSet):
    queryset = StockConsignacionCliente.objects.all()
    serializer_class = StockConsignacionClienteSerializer

    def get_queryset(self):
        # R-CODE-1
        return StockConsignacionCliente.objects.filter(id_empresa__in=_empresas(self.request))


class StockConsignacionProveedorViewSet(BaseModelViewSet):
    queryset = StockConsignacionProveedor.objects.all()
    serializer_class = StockConsignacionProveedorSerializer

    def get_queryset(self):
        # R-CODE-1
        return StockConsignacionProveedor.objects.filter(id_empresa__in=_empresas(self.request))
