import pytest
import httpx
from django.urls import reverse
from django.test import Client

pytestmark = pytest.mark.django_db

BASE_URL = "http://localhost:8000/api/"
TOKEN_URL = "http://localhost:8000/api/auth/token/"


def test_login_invalid_credentials():
    client = Client()
    response = client.post(reverse('token_obtain_pair'), {'username': 'wrong', 'password': 'wrong'})
    assert response.status_code == 401
    assert "access" not in response.json()

def test_login_valid(test_user):
    client = Client()
    response = client.post(reverse('token_obtain_pair'), {'username': 'testuser', 'password': 'testpass123'})
    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()
    token = response.json()["access"]
    # Probar acceso a endpoint protegido (usuarios) usando client
    client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    users_response = client.get('/api/core/usuarios/')
    assert users_response.status_code in (200, 403)  # 200 si tiene permisos, 403 si no