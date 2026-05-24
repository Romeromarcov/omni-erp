from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AsignacionHorarioViewSet,
    HorarioTrabajoViewSet,
    RegistroAsistenciaViewSet,
    ResumenAsistenciaDiarioViewSet,
)

router = DefaultRouter()
router.register(r"horarios-trabajo", HorarioTrabajoViewSet)
router.register(r"asignaciones-horario", AsignacionHorarioViewSet)
router.register(r"registros-asistencia", RegistroAsistenciaViewSet)
router.register(r"resumenes-asistencia-diario", ResumenAsistenciaDiarioViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
