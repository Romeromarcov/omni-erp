from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoriaTicketViewSet, TicketSoporteViewSet, InteraccionTicketViewSet,
    BaseConocimientoArticuloViewSet, FeedbackClienteViewSet
)

router = DefaultRouter()
router.register(r'categorias-ticket', CategoriaTicketViewSet)
router.register(r'tickets-soporte', TicketSoporteViewSet)
router.register(r'interacciones-ticket', InteraccionTicketViewSet)
router.register(r'articulos-conocimiento', BaseConocimientoArticuloViewSet)
router.register(r'feedback-cliente', FeedbackClienteViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
