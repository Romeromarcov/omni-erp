"""Fase 0 — pruebas del scaffold de la app aislada ``apps.cxc_lubrikca``.

Verifican que la app está registrada, su router montado en ``/api/cxc-lubrikca/``
y el health check responde. Cubren el código nuevo de la Fase 0 (apps.py + router).
"""
import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient


@pytest.mark.unit
def test_app_cxc_lubrikca_registrada():
    """La app aislada está en el registro de Django (INSTALLED_APPS)."""
    config = django_apps.get_app_config("cxc_lubrikca")
    assert config.name == "apps.cxc_lubrikca"
    assert config.verbose_name


@pytest.mark.django_db
def test_health_check_responde_ok(user_a):
    """GET /api/cxc-lubrikca/health/ → 200 con status ok y módulo identificado."""
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get("/api/cxc-lubrikca/health/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["modulo"] == "cxc_lubrikca"
