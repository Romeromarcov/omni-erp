"""M-SEC-9: el scope '*' de CapabilityToken solo aplica a tokens internos o
creados por superusuario Omni."""

import pytest

from django.contrib.auth import get_user_model

from apps.core.models import CapabilityToken


@pytest.mark.django_db
def test_wildcard_token_interno_sin_creador_concede(empresa_a):
    t = CapabilityToken.objects.create(empresa=empresa_a, nombre="interno", scopes=["*"])
    assert t.has_scope("ventas:write") is True


@pytest.mark.django_db
def test_wildcard_token_de_usuario_normal_no_concede(empresa_a, user_a):
    t = CapabilityToken.objects.create(
        empresa=empresa_a, nombre="user-token", scopes=["*"], creado_por=user_a
    )
    assert t.has_scope("ventas:write") is False
    # El scope explícito sí funciona.
    t2 = CapabilityToken.objects.create(
        empresa=empresa_a, nombre="user-token-2", scopes=["ventas:write"], creado_por=user_a
    )
    assert t2.has_scope("ventas:write") is True


@pytest.mark.django_db
def test_wildcard_token_de_superusuario_concede(empresa_a):
    User = get_user_model()
    su = User.objects.create_user(username="su_cap", password="x", is_active=True)
    su.es_superusuario_omni = True
    su.save()
    t = CapabilityToken.objects.create(
        empresa=empresa_a, nombre="su-token", scopes=["*"], creado_por=su
    )
    assert t.has_scope("ventas:write") is True
