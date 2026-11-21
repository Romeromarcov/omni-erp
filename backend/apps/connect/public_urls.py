"""URLs públicas (sin autenticación) de Omni Connect (``/api/public/connect/``)."""

from django.urls import path

from .views import PublicLeadCreateView, PublicPerfilDetailView, PublicPerfilVCardView

urlpatterns = [
    path("<str:slug>/", PublicPerfilDetailView.as_view(), name="connect-public-perfil"),
    path("<str:slug>/vcard/", PublicPerfilVCardView.as_view(), name="connect-public-vcard"),
    path("<str:slug>/leads/", PublicLeadCreateView.as_view(), name="connect-public-lead-create"),
]
