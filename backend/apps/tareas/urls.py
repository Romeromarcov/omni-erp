from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AreaOperativaViewSet,
    ConfiguracionSeguimientoView,
    EjecutarSeguimientoView,
    MinutaReunionViewSet,
    PlantillaTareaRecurrenteViewSet,
    ProyectoViewSet,
    RegistroAlertaTareaViewSet,
    ResumenEjecutivoTareasView,
    SeccionProyectoViewSet,
    TareaViewSet,
)

router = DefaultRouter()
router.register("areas", AreaOperativaViewSet, basename="tareas-areas")
router.register("proyectos", ProyectoViewSet, basename="tareas-proyectos")
router.register("secciones", SeccionProyectoViewSet, basename="tareas-secciones")
router.register("items", TareaViewSet, basename="tareas-items")
router.register("recurrentes", PlantillaTareaRecurrenteViewSet, basename="tareas-recurrentes")
router.register("minutas", MinutaReunionViewSet, basename="tareas-minutas")
router.register("alertas", RegistroAlertaTareaViewSet, basename="tareas-alertas")

urlpatterns = [
    path("configuracion/", ConfiguracionSeguimientoView.as_view(), name="tareas-config"),
    path("resumen/", ResumenEjecutivoTareasView.as_view(), name="tareas-resumen"),
    path(
        "seguimiento/ejecutar/",
        EjecutarSeguimientoView.as_view(),
        name="tareas-ejecutar-seguimiento",
    ),
    path("", include(router.urls)),
]
