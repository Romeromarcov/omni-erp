from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AlmacenViewSet, UbicacionAlmacenViewSet

router = DefaultRouter()
router.register(r'almacenes', AlmacenViewSet)
router.register(r'ubicaciones-almacen', UbicacionAlmacenViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
