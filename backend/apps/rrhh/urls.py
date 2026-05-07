from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EmpleadoViewSet, CargoViewSet, BeneficioViewSet,
    BeneficioEmpleadoViewSet, TipoLicenciaViewSet, LicenciaEmpleadoViewSet
)

router = DefaultRouter()
router.register(r'empleados', EmpleadoViewSet)
router.register(r'cargos', CargoViewSet)
router.register(r'beneficios', BeneficioViewSet)
router.register(r'beneficios-empleado', BeneficioEmpleadoViewSet)
router.register(r'tipos-licencia', TipoLicenciaViewSet)
router.register(r'licencias-empleado', LicenciaEmpleadoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
