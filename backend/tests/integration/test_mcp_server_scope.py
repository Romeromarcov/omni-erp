"""
Backfill de cobertura — apps/core/mcp_server.py (plan "Cero Dudas", COV/mcp + A2-8).

Foco en el **enforcement de scope del MCP**, que es seguridad-crítica:

- ``_resolve_token``: valida el CapabilityToken y devuelve el contexto del tenant;
  rechaza UUID inválido, token inexistente, inactivo (revocado) y expirado.
- **Gate del comodín ``*`` (SEC-NEW-4 / M-SEC-9):** un token con ``scopes=["*"]``
  creado por un usuario normal NO debe conceder acceso total — el ``*`` se filtra en
  ``_resolve_token``; solo es efectivo para tokens de sistema (``creado_por=None``) o
  de superusuario Omni.
- ``_require_scope``: PermissionError si falta el scope o el contexto es None; pasa con
  el scope exacto o con ``*`` efectivo.
- A nivel de herramienta: ``omni_ping`` (token inválido → PermissionError) y
  ``omni_get_empresas`` (exige ``core:read``).
"""
import datetime
import uuid

import pytest

from django.utils import timezone

from apps.core.mcp_server import (
    _require_scope,
    _resolve_token,
    omni_get_empresas,
    omni_ping,
)
from apps.core.models import CapabilityToken

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _token(empresa, scopes, *, activo=True, expires_at=None, creado_por=None):
    return CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-test",
        scopes=scopes,
        activo=activo,
        expires_at=expires_at,
        creado_por=creado_por,
    )


# ── _resolve_token ────────────────────────────────────────────────────────────

class TestResolveToken:
    def test_token_valido_devuelve_contexto(self, empresa_a):
        tok = _token(empresa_a, ["crm:read"])
        ctx = _resolve_token(str(tok.token))
        assert ctx is not None
        assert ctx["tenant_id"] == str(empresa_a.id_empresa)
        assert ctx["empresa_id"] == str(empresa_a.id_empresa)
        assert ctx["scopes"] == ["crm:read"]
        assert ctx["actor_id"].startswith("mcp-token:")

    def test_uuid_invalido_devuelve_none(self):
        assert _resolve_token("no-es-uuid") is None

    def test_token_inexistente_devuelve_none(self):
        assert _resolve_token(str(uuid.uuid4())) is None

    def test_token_inactivo_devuelve_none(self, empresa_a):
        """Revocación inmediata: activo=False → no resuelve."""
        tok = _token(empresa_a, ["crm:read"], activo=False)
        assert _resolve_token(str(tok.token)) is None

    def test_token_expirado_devuelve_none(self, empresa_a):
        pasado = timezone.now() - datetime.timedelta(days=1)
        tok = _token(empresa_a, ["crm:read"], expires_at=pasado)
        assert _resolve_token(str(tok.token)) is None


# ── Gate del comodín '*' (SEC-NEW-4) ──────────────────────────────────────────

class TestComodinGate:
    def test_comodin_de_token_de_sistema_se_conserva(self, empresa_a):
        """creado_por=None → token de sistema → '*' efectivo."""
        tok = _token(empresa_a, ["*"], creado_por=None)
        ctx = _resolve_token(str(tok.token))
        assert ctx["scopes"] == ["*"]

    def test_comodin_de_usuario_normal_se_filtra(self, empresa_a, user_a):
        """Usuario normal NO puede auto-otorgarse '*' → se elimina del contexto."""
        assert getattr(user_a, "es_superusuario_omni", False) is False
        tok = _token(empresa_a, ["*", "crm:read"], creado_por=user_a)
        ctx = _resolve_token(str(tok.token))
        assert "*" not in ctx["scopes"]
        assert ctx["scopes"] == ["crm:read"]

    def test_comodin_filtrado_no_concede_acceso(self, empresa_a, user_a):
        """Tras filtrar el '*' auto-otorgado, _require_scope debe negar."""
        tok = _token(empresa_a, ["*"], creado_por=user_a)
        ctx = _resolve_token(str(tok.token))
        with pytest.raises(PermissionError):
            _require_scope(ctx, "ventas:write")


# ── _require_scope ────────────────────────────────────────────────────────────

class TestRequireScope:
    def test_contexto_none_lanza(self):
        with pytest.raises(PermissionError):
            _require_scope(None, "crm:read")

    def test_scope_faltante_lanza(self):
        with pytest.raises(PermissionError):
            _require_scope({"scopes": ["crm:read"]}, "ventas:write")

    def test_scope_presente_pasa(self):
        _require_scope({"scopes": ["crm:read", "ventas:write"]}, "ventas:write")

    def test_comodin_efectivo_pasa_cualquier_scope(self):
        _require_scope({"scopes": ["*"]}, "lo:que:sea")


# ── Nivel de herramienta ──────────────────────────────────────────────────────

class TestToolsScope:
    def test_omni_ping_token_invalido_lanza(self):
        with pytest.raises(PermissionError):
            omni_ping("no-es-uuid")

    def test_omni_ping_token_valido_ok(self, empresa_a):
        tok = _token(empresa_a, ["core:read"])
        res = omni_ping(str(tok.token))
        assert res["status"] == "ok"
        assert res["tenant_id"] == str(empresa_a.id_empresa)

    def test_omni_get_empresas_sin_scope_lanza(self, empresa_a):
        tok = _token(empresa_a, ["ventas:read"])  # falta core:read
        with pytest.raises(PermissionError):
            omni_get_empresas(str(tok.token))

    def test_omni_get_empresas_con_scope_ok(self, empresa_a):
        tok = _token(empresa_a, ["core:read"])
        empresas = omni_get_empresas(str(tok.token))
        assert isinstance(empresas, list)
