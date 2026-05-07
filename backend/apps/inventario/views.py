

from rest_framework import viewsets
from .models import (
    UnidadMedida, CategoriaProducto, Producto, VarianteProducto,
    StockActual, MovimientoInventario, ConversionUnidadMedida,
    StockConsignacionCliente, StockConsignacionProveedor
)
from .serializers import (
    UnidadMedidaSerializer, CategoriaProductoSerializer, ProductoSerializer,
    VarianteProductoSerializer, StockActualSerializer,
    MovimientoInventarioSerializer, ConversionUnidadMedidaSerializer,
    StockConsignacionClienteSerializer, StockConsignacionProveedorSerializer
)
from apps.core.viewsets import BaseModelViewSet


class UnidadMedidaViewSet(BaseModelViewSet):
    queryset = UnidadMedida.objects.all()
    serializer_class = UnidadMedidaSerializer


class CategoriaProductoViewSet(BaseModelViewSet):
    queryset = CategoriaProducto.objects.all()
    serializer_class = CategoriaProductoSerializer


class ProductoViewSet(BaseModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer

    def get_queryset(self):
        queryset = Producto.objects.all()
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            queryset = queryset.filter(id_empresa=empresa_id)
        return queryset


class VarianteProductoViewSet(BaseModelViewSet):
    queryset = VarianteProducto.objects.all()
    serializer_class = VarianteProductoSerializer


class StockActualViewSet(BaseModelViewSet):
    queryset = StockActual.objects.all()
    serializer_class = StockActualSerializer


class MovimientoInventarioViewSet(BaseModelViewSet):
    queryset = MovimientoInventario.objects.all()
    serializer_class = MovimientoInventarioSerializer


class ConversionUnidadMedidaViewSet(BaseModelViewSet):
    queryset = ConversionUnidadMedida.objects.all()
    serializer_class = ConversionUnidadMedidaSerializer


class StockConsignacionClienteViewSet(BaseModelViewSet):
    queryset = StockConsignacionCliente.objects.all()
    serializer_class = StockConsignacionClienteSerializer


class StockConsignacionProveedorViewSet(BaseModelViewSet):
    queryset = StockConsignacionProveedor.objects.all()
    serializer_class = StockConsignacionProveedorSerializer
