"""Router principal de CxC API."""

import logging
from datetime import date

from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

logger = logging.getLogger(__name__)


def _health_check_view(request):
    """Health check para el módulo CxC."""
    checks = {}
    try:
        from apps.cxc.models import GestionCobranza

        GestionCobranza.objects.exists()
        checks["db"] = "ok"
    except Exception:
        logger.warning("cxc health check fallo (%s)", "db", exc_info=True)
        checks["db"] = "error"
    try:
        from django.core.cache import cache

        cache.set("cxc:health", "ok", timeout=5)
        checks["cache"] = "ok"
    except Exception:
        logger.warning("cxc health check fallo (%s)", "cache", exc_info=True)
        checks["cache"] = "error"
    try:
        from apps.finanzas.models import TasaCambio

        tasa = TasaCambio.objects.filter(fecha_tasa=date.today()).exists()
        checks["tasa_hoy"] = "ok" if tasa else "sin_tasa"
    except Exception:
        logger.warning("cxc health check fallo (%s)", "tasa_hoy", exc_info=True)
        checks["tasa_hoy"] = "error"
    all_ok = all(v == "ok" for v in checks.values())
    return JsonResponse({"status": "ok" if all_ok else "degraded", "checks": checks})


from apps.cxc.api.cartera import CarteraDashboardView
from apps.cxc.api.cobranza import GestionCobranzaViewSet, PlantillaCobranzaViewSet
from apps.cxc.api.acuerdos import AcuerdoPagoViewSet
from apps.cxc.api.fraccionamiento import LoteFraccionadoViewSet, VentaFraccionadaViewSet
from apps.cxc.api.agente import CobranzaAgenteView

router = DefaultRouter()
router.register("gestiones", GestionCobranzaViewSet, basename="cxc-gestiones")
router.register("acuerdos", AcuerdoPagoViewSet, basename="cxc-acuerdos")
router.register("plantillas", PlantillaCobranzaViewSet, basename="cxc-plantillas")
router.register("lotes", LoteFraccionadoViewSet, basename="cxc-lotes")
router.register("ventas-fraccionadas", VentaFraccionadaViewSet, basename="cxc-ventas-frac")

urlpatterns = [
    *router.urls,
    path("cartera/dashboard/", CarteraDashboardView.as_view(), name="cxc-cartera-dashboard"),
    path("agente/", CobranzaAgenteView.as_view(), name="cxc-agente"),
    path("health/", _health_check_view, name="cxc-health"),
]
