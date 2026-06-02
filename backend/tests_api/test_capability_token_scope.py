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


# ── SEC-NEW-4: el gate del comodín está cableado en el enforcement MCP ──────────


@pytest.mark.django_db
def test_mcp_resolver_filtra_comodin_de_usuario_normal(empresa_a, user_a):
    """Un token de empresa con scopes=['*'] no debe conceder acceso MCP total."""
    from apps.core.mcp_server import _require_scope, _resolve_token

    t = CapabilityToken.objects.create(
        empresa=empresa_a, nombre="user-mcp", scopes=["*"], creado_por=user_a
    )
    ctx = _resolve_token(str(t.token))
    assert "*" not in ctx["scopes"]  # comodín filtrado
    with pytest.raises(PermissionError):
        _require_scope(ctx, "ventas:write")


@pytest.mark.django_db
def test_mcp_resolver_conserva_comodin_de_sistema(empresa_a):
    """Un token interno (sin creador) con '*' sí concede acceso total vía MCP."""
    from apps.core.mcp_server import _require_scope, _resolve_token

    t = CapabilityToken.objects.create(empresa=empresa_a, nombre="sistema", scopes=["*"])
    ctx = _resolve_token(str(t.token))
    assert "*" in ctx["scopes"]
    _require_scope(ctx, "ventas:write")  # no lanza
