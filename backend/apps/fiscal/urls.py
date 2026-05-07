from rest_framework import routers
from .views import (
    ImpuestoViewSet, ConfiguracionImpuestoViewSet, RetencionViewSet, ContribucionParafiscalViewSet,
    ImpuestoEmpresaActivaViewSet, RetencionEmpresaActivaViewSet, ContribucionEmpresaActivaViewSet,
    EmpresaContribucionParafiscalViewSet, ConfiguracionRetencionViewSet
)

router = routers.DefaultRouter()
router.register(r'impuestos', ImpuestoViewSet)
router.register(r'configuracion-impuestos', ConfiguracionImpuestoViewSet)
router.register(r'retenciones', RetencionViewSet)
router.register(r'contribuciones-parafiscales', ContribucionParafiscalViewSet)
router.register(r'impuestos-empresa-activa', ImpuestoEmpresaActivaViewSet)
router.register(r'retenciones-empresa-activa', RetencionEmpresaActivaViewSet)
router.register(r'contribuciones-empresa-activa', ContribucionEmpresaActivaViewSet)
router.register(r'empresa-contribuciones-parafiscales', EmpresaContribucionParafiscalViewSet)
router.register(r'configuracion-retenciones', ConfiguracionRetencionViewSet)

urlpatterns = router.urls
