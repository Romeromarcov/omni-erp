"""Test del healthcheck (NEW-INFRA-5)."""

import pytest

from rest_framework.test import APIClient


def test_health_sin_auth_devuelve_200(db):
    """El healthcheck no requiere autenticación y responde ok."""
    resp = APIClient().get("/api/health/")
    assert resp.status_code == 200
    assert resp.data["status"] == "ok"


@pytest.mark.django_db
def test_health_db_check_ok():
    """Con ?db=1 verifica conectividad a la BD."""
    resp = APIClient().get("/api/health/?db=1")
    assert resp.status_code == 200
    assert resp.data["db"] == "ok"
