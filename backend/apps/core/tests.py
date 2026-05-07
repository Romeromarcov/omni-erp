import pytest
import httpx
from django.contrib.auth import get_user_model
from apps.core.models import Empresa, Moneda

pytestmark = pytest.mark.django_db

BASE_URL = "http://localhost:8000/api/"
TOKEN_URL = "http://localhost:8000/api/token/"

@pytest.fixture
def test_user(db):
    moneda = Moneda.objects.create(nombre="Dólar", codigo="USD", simbolo="$", es_base=True)
    empresa = Empresa.objects.create(nombre="Empresa Test", rif="J123456789", moneda_base=moneda)
    User = get_user_model()
    user = User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="testuser@example.com",
        empresa=empresa,
        moneda=moneda,
        is_active=True
    )
    return user

def test_login_invalid_credentials():
    response = httpx.post(TOKEN_URL, data={"username": "wrong", "password": "wrong"})
    assert response.status_code == 401
    assert "access" not in response.json()

def test_login_valid(test_user):
    response = httpx.post(TOKEN_URL, data={"username": "testuser", "password": "testpass123"})
    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()
    token = response.json()["access"]
    # Probar acceso a endpoint protegido (usuarios)
    users_url = BASE_URL + "core/usuarios/"
    r = httpx.get(users_url, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200, 403)  # 200 si tiene permisos, 403 si no
from django.test import TestCase

# Create your tests here.
