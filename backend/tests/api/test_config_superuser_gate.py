"""H-SEC-6 / M-API-2: escritura de catálogos globales solo por superusuario Omni."""

import pytest

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def superuser_omni(db):
    User = get_user_model()
    su = User.objects.create_user(username="su_cfg", password="x", is_active=True)
    su.es_superusuario_omni = True
    su.save()
    return su


@pytest.mark.django_db
def test_tipo_documento_no_modificable_por_no_superuser(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.post(
        "/api/configuracion/tipos-documento/",
        {"codigo": "X1", "nombre": "Test", "modulo_origen": "core"},
        format="json",
    )
    assert resp.status_code == 403
    from apps.configuracion_motor.models import TipoDocumento

    assert not TipoDocumento.objects.filter(codigo="X1").exists()


@pytest.mark.django_db
def test_tipo_documento_modificable_por_superuser(superuser_omni):
    client = APIClient()
    client.force_authenticate(user=superuser_omni)
    resp = client.post(
        "/api/configuracion/tipos-documento/",
        {"codigo": "X2", "nombre": "Test", "modulo_origen": "core"},
        format="json",
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_parametro_global_no_modificable_por_no_superuser(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.post(
        "/api/configuracion/parametros-sistema/",
        {"nombre_parametro": "G", "codigo_parametro": "g.test", "valor_parametro": "1", "tipo_dato": "TEXTO"},
        format="json",
    )
    # id_empresa ausente → fila global → requiere superusuario.
    assert resp.status_code == 403
