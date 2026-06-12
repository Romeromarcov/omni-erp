"""
H-API-1 / H-API-2: id_empresa es read-only en los serializers head de ventas y
compras, y los ViewSets inyectan la empresa del usuario (EmpresaInjectMixin).
"""

import pytest

pytestmark = pytest.mark.tenant


def _ventas_serializers():
    from apps.ventas import serializers as s

    return [
        s.PedidoSerializer,
        s.NotaVentaSerializer,
        s.FacturaFiscalSerializer,
        s.CotizacionSerializer,
        s.NotaCreditoVentaSerializer,
        s.DevolucionVentaSerializer,
        s.NotaCreditoFiscalSerializer,
        s.ListaPrecioSerializer,
    ]


def _compras_serializers():
    from apps.compras import serializers as s

    return [
        s.OrdenCompraSerializer,
        s.RecepcionMercanciaSerializer,
        s.FacturaCompraSerializer,
        s.RequisicionCompraSerializer,
        s.SolicitudCotizacionSerializer,
    ]


@pytest.mark.django_db
def test_id_empresa_read_only_en_serializers_head():
    for cls in _ventas_serializers() + _compras_serializers():
        fields = cls().fields
        assert "id_empresa" in fields, f"{cls.__name__} no tiene id_empresa"
        assert fields["id_empresa"].read_only, (
            f"{cls.__name__}.id_empresa debe ser read_only (H-API): un cliente no "
            f"puede crear registros en otra empresa vía el payload."
        )


def test_viewsets_usan_empresa_inject_mixin():
    from apps.core.viewsets import EmpresaInjectMixin
    from apps.ventas import views as v
    from apps.compras import views as c

    for vs in [v.PedidoViewSet, v.NotaVentaViewSet, v.FacturaFiscalViewSet, v.CotizacionViewSet]:
        assert issubclass(vs, EmpresaInjectMixin), f"{vs.__name__} debe usar EmpresaInjectMixin"
    for vs in [c.OrdenCompraViewSet, c.FacturaCompraViewSet]:
        assert issubclass(vs, EmpresaInjectMixin), f"{vs.__name__} debe usar EmpresaInjectMixin"
