"""Router del subproyecto CxC Lubrikca.

App aislada montada en ``/api/cxc-lubrikca/`` y gated en frontend por el perfil
``cobranza`` (``appProfile.ts``). Los ViewSets se irán registrando por fase.
"""
from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter


def _health_check_view(request):
    """Health check del módulo CxC Lubrikca (sin dependencias de BD aún)."""
    return JsonResponse({"status": "ok", "modulo": "cxc_lubrikca"})


router = DefaultRouter()
# Fase 1+: router.register("descuentos", DescuentoMarcaCategoriaViewSet, ...)

urlpatterns = [
    *router.urls,
    path("health/", _health_check_view, name="cxc-lubrikca-health"),
]
