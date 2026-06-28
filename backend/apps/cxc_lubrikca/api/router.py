"""Router del subproyecto CxC Lubrikca.

App aislada montada en ``/api/cxc-lubrikca/`` y gated en frontend por el perfil
``cobranza`` (``appProfile.ts``). Los ViewSets se registran por fase.
"""
from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

from .operacion_viewsets import (
    BandejaFacturacionViewSet,
    LineaPedidoLubrikcaViewSet,
    PagoLubrikcaViewSet,
    PedidoLubrikcaViewSet,
    PrecioListaLubrikcaViewSet,
    VinculacionViewSet,
)
from .viewsets import (
    DescuentoBCVCompletoViewSet,
    DescuentoMarcaCategoriaViewSet,
    FeriadoViewSet,
    MetodoPagoViewSet,
    PromocionPrimeraCompraViewSet,
    ReglaRecurrenciaViewSet,
)


def _health_check_view(request):
    """Health check del módulo CxC Lubrikca (sin dependencias de BD aún)."""
    return JsonResponse({"status": "ok", "modulo": "cxc_lubrikca"})


router = DefaultRouter()
router.register(
    "descuentos-marca-categoria", DescuentoMarcaCategoriaViewSet, basename="cxcl-descuentos"
)
router.register(
    "descuentos-bcv-completo", DescuentoBCVCompletoViewSet, basename="cxcl-descuentos-bcv"
)
router.register(
    "promociones-primera-compra", PromocionPrimeraCompraViewSet, basename="cxcl-promociones"
)
router.register("reglas-recurrencia", ReglaRecurrenciaViewSet, basename="cxcl-recurrencia")
router.register("feriados", FeriadoViewSet, basename="cxcl-feriados")
router.register("metodos-pago", MetodoPagoViewSet, basename="cxcl-metodos-pago")

# Fase 3 — operación (espejo + cierre híbrido)
router.register("pedidos", PedidoLubrikcaViewSet, basename="cxcl-pedidos")
router.register("lineas-pedido", LineaPedidoLubrikcaViewSet, basename="cxcl-lineas-pedido")
router.register("precios-lista", PrecioListaLubrikcaViewSet, basename="cxcl-precios-lista")
router.register("pagos", PagoLubrikcaViewSet, basename="cxcl-pagos")
router.register("vinculaciones", VinculacionViewSet, basename="cxcl-vinculaciones")
router.register("bandeja", BandejaFacturacionViewSet, basename="cxcl-bandeja")

urlpatterns = [
    *router.urls,
    path("health/", _health_check_view, name="cxc-lubrikca-health"),
]
