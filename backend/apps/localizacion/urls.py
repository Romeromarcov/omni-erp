"""URLs del framework de localización (PR-25 / ADR-007)."""

from django.urls import path

from .views import EstadoLocalizacionView

urlpatterns = [
    path("estado/", EstadoLocalizacionView.as_view(), name="localizacion-estado"),
]
