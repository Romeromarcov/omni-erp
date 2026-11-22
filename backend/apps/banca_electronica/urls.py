from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LotePagoBancarioViewSet, ValidarCuentaVeView, ValidarReferenciaView

router = DefaultRouter()
router.register(r"lotes-pago", LotePagoBancarioViewSet, basename="lotes-pago")

urlpatterns = [
    path("validar-referencia/", ValidarReferenciaView.as_view(), name="banca-validar-referencia"),
    path("validar-cuenta-ve/", ValidarCuentaVeView.as_view(), name="banca-validar-cuenta-ve"),
    path("", include(router.urls)),
]
