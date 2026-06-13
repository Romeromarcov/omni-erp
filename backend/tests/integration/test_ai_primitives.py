"""
Tests para las primitivas AI-nativas de Omni — Semana 4.

Cubre:
  1. Event Store (apps/core/events.py) — build_event, publish en modo stub.
  2. CapabilityToken — CRUD, is_expired, has_scope, mark_used.
  3. Estructura del MCP server — importación sin errores, herramientas registradas.

Los tests de eventos se ejecutan siempre en modo stub (sin Redpanda real),
garantizados por la ausencia de KAFKA_BOOTSTRAP_SERVERS en el entorno de test.

Los tests del MCP server solo verifican la estructura (no el protocolo completo)
para no requerir un cliente MCP real.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

pytestmark = pytest.mark.integration


# ── Tests de Event Store ──────────────────────────────────────────────────────


class TestBuildEvent:
    """Verifica que build_event produce el sobre canónico correcto."""

    def test_campos_obligatorios_presentes(self):
        from apps.core.events import build_event

        evt = build_event(
            event_type="omni.core.empresa.creada",
            tenant_id="tenant-001",
            payload={"nombre": "Empresa Test"},
        )

        assert "event_id" in evt
        assert "event_type" in evt
        assert "schema_version" in evt
        assert "occurred_at" in evt
        assert "tenant_id" in evt
        assert "actor_id" in evt
        assert "payload" in evt
        assert "metadata" in evt

    def test_event_type_correcto(self):
        from apps.core.events import build_event

        evt = build_event(
            event_type="omni.ventas.pedido.confirmado",
            tenant_id="tenant-001",
            payload={},
        )
        assert evt["event_type"] == "omni.ventas.pedido.confirmado"

    def test_tenant_id_se_propaga(self):
        from apps.core.events import build_event

        evt = build_event(event_type="omni.test.a.b", tenant_id="empresa-xyz", payload={})
        assert evt["tenant_id"] == "empresa-xyz"

    def test_actor_id_default_es_system(self):
        from apps.core.events import build_event

        evt = build_event(event_type="omni.test.a.b", tenant_id="t", payload={})
        assert evt["actor_id"] == "system"

    def test_actor_id_personalizable(self):
        from apps.core.events import build_event

        evt = build_event(
            event_type="omni.test.a.b",
            tenant_id="t",
            payload={},
            actor_id="user-abc",
        )
        assert evt["actor_id"] == "user-abc"

    def test_event_id_es_uuid_valido(self):
        from apps.core.events import build_event

        evt = build_event(event_type="omni.test.a.b", tenant_id="t", payload={})
        # Debe poder parsearse como UUID sin error
        parsed = uuid.UUID(evt["event_id"])
        assert str(parsed) == evt["event_id"]

    def test_event_ids_son_unicos(self):
        from apps.core.events import build_event

        ids = {
            build_event(event_type="omni.test.a.b", tenant_id="t", payload={})["event_id"]
            for _ in range(50)
        }
        assert len(ids) == 50

    def test_payload_se_preserva(self):
        from apps.core.events import build_event

        payload = {"campo": "valor", "numero": 42, "lista": [1, 2, 3]}
        evt = build_event(event_type="omni.test.a.b", tenant_id="t", payload=payload)
        assert evt["payload"] == payload

    def test_metadata_default_es_dict_vacio(self):
        from apps.core.events import build_event

        evt = build_event(event_type="omni.test.a.b", tenant_id="t", payload={})
        assert evt["metadata"] == {}

    def test_occurred_at_es_iso8601(self):
        from apps.core.events import build_event

        evt = build_event(event_type="omni.test.a.b", tenant_id="t", payload={})
        # Debe parsear como datetime ISO8601
        from datetime import datetime

        dt = datetime.fromisoformat(evt["occurred_at"])
        assert dt is not None


class TestPublishEventStub:
    """Verifica publish() en modo stub (sin Kafka real)."""

    def test_publish_sin_broker_retorna_evento(self):
        """Sin KAFKA_BOOTSTRAP_SERVERS, publish devuelve el evento sin errores."""
        import apps.core.events as events_module

        original = events_module.KAFKA_BOOTSTRAP_SERVERS
        try:
            events_module.KAFKA_BOOTSTRAP_SERVERS = ""  # modo stub
            evt = events_module.publish(
                event_type="omni.core.empresa.creada",
                tenant_id="empresa-test",
                payload={"nombre": "Test"},
            )
            assert evt["event_type"] == "omni.core.empresa.creada"
            assert evt["tenant_id"] == "empresa-test"
        finally:
            events_module.KAFKA_BOOTSTRAP_SERVERS = original

    def test_publish_con_broker_fallido_no_lanza_excepcion(self):
        """Si el broker falla, publish NO lanza excepción (no debe romper la transacción)."""
        import apps.core.events as events_module

        original = events_module.KAFKA_BOOTSTRAP_SERVERS
        try:
            # Simular que hay un servidor configurado pero que falla
            events_module.KAFKA_BOOTSTRAP_SERVERS = "localhost:9999"
            with patch("apps.core.events._get_producer") as mock_producer:
                mock_prod = MagicMock()
                mock_prod.produce.side_effect = Exception("Connection refused")
                mock_producer.return_value = mock_prod

                # NO debe lanzar excepción
                evt = events_module.publish(
                    event_type="omni.test.a.b",
                    tenant_id="t",
                    payload={},
                )
                assert "event_id" in evt
        finally:
            events_module.KAFKA_BOOTSTRAP_SERVERS = original

    def test_constantes_de_eventos_existen(self):
        """Los catálogos de tipos de evento están definidos."""
        from apps.core.events import CobranzaEvents, CoreEvents, InventarioEvents, VentasEvents

        assert CoreEvents.EMPRESA_CREADA == "omni.core.empresa.creada"
        assert VentasEvents.PEDIDO_CONFIRMADO == "omni.ventas.pedido.confirmado"
        assert InventarioEvents.MOVIMIENTO_REGISTRADO == "omni.inventario.movimiento.registrado"
        assert CobranzaEvents.PAGO_TOTAL == "omni.cobranza.pago.total"


# ── Tests de CapabilityToken ──────────────────────────────────────────────────


class TestCapabilityToken:
    """Verifica el modelo CapabilityToken."""

    @pytest.fixture
    def token_activo(self, db, empresa_a):
        from apps.core.models import CapabilityToken

        return CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Agente de cobranza test",
            scopes=["crm:read", "cxc:read"],
            expires_at=timezone.now() + timedelta(days=90),
        )

    @pytest.fixture
    def token_expirado(self, db, empresa_a):
        from apps.core.models import CapabilityToken

        return CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Token expirado",
            scopes=["crm:read"],
            expires_at=timezone.now() - timedelta(days=1),
        )

    @pytest.fixture
    def token_sin_expiracion(self, db, empresa_a):
        from apps.core.models import CapabilityToken

        return CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Token interno",
            scopes=["*"],
            expires_at=None,
        )

    def test_token_se_crea_con_uuid(self, token_activo):
        assert token_activo.token is not None
        assert isinstance(token_activo.token, uuid.UUID)

    def test_token_activo_no_expirado(self, token_activo):
        assert not token_activo.is_expired()

    def test_token_expirado_detectado(self, token_expirado):
        assert token_expirado.is_expired()

    def test_token_sin_expiracion_nunca_expira(self, token_sin_expiracion):
        assert not token_sin_expiracion.is_expired()

    def test_has_scope_correcto(self, token_activo):
        assert token_activo.has_scope("crm:read")
        assert token_activo.has_scope("cxc:read")
        assert not token_activo.has_scope("ventas:write")

    def test_scope_wildcard_tiene_todo(self, token_sin_expiracion):
        assert token_sin_expiracion.has_scope("crm:read")
        assert token_sin_expiracion.has_scope("ventas:write")
        assert token_sin_expiracion.has_scope("cualquier:cosa")

    def test_mark_used_actualiza_ultimo_uso(self, db, token_activo):
        from apps.core.models import CapabilityToken

        assert token_activo.ultimo_uso is None
        token_activo.mark_used()
        token_activo.refresh_from_db()
        assert token_activo.ultimo_uso is not None

    def test_soft_delete_desactiva_token(self, token_activo):
        token_activo.soft_delete()
        assert token_activo.activo is False

    def test_tokens_son_unicos(self, db, empresa_a):
        from apps.core.models import CapabilityToken

        t1 = CapabilityToken.objects.create(empresa=empresa_a, nombre="T1", scopes=[])
        t2 = CapabilityToken.objects.create(empresa=empresa_a, nombre="T2", scopes=[])
        assert t1.token != t2.token

    def test_empresa_tiene_capability_tokens_related(self, db, empresa_a, token_activo):
        assert empresa_a.capability_tokens.count() >= 1

    def test_str_incluye_nombre_y_token_parcial(self, token_activo):
        s = str(token_activo)
        assert "Agente de cobranza test" in s
        assert str(token_activo.token)[:8] in s


# ── Tests de estructura del MCP Server ───────────────────────────────────────


class TestMCPServerStructure:
    """Verifica que el MCP server importa correctamente y tiene las herramientas esperadas."""

    def test_mcp_server_importa_sin_errores(self):
        """El módulo mcp_server debe importar sin excepciones."""
        import apps.core.mcp_server as mcp_module  # noqa: F401

    def test_mcp_available_flag_existe(self):
        from apps.core.mcp_server import MCP_AVAILABLE

        assert isinstance(MCP_AVAILABLE, bool)

    def test_mcp_instance_existe_si_disponible(self):
        from apps.core.mcp_server import MCP_AVAILABLE, mcp

        if MCP_AVAILABLE:
            assert mcp is not None
        else:
            assert mcp is None

    def test_resolve_token_retorna_none_para_token_invalido(self, db):
        from apps.core.mcp_server import _resolve_token

        resultado = _resolve_token("token-inexistente-12345")
        assert resultado is None

    def test_resolve_token_retorna_none_para_token_expirado(self, db, empresa_a):
        from apps.core.models import CapabilityToken
        from apps.core.mcp_server import _resolve_token

        token_exp = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Expirado",
            scopes=["crm:read"],
            expires_at=timezone.now() - timedelta(hours=1),
        )
        resultado = _resolve_token(str(token_exp.token))
        assert resultado is None

    def test_resolve_token_retorna_contexto_valido(self, db, empresa_a):
        from apps.core.models import CapabilityToken
        from apps.core.mcp_server import _resolve_token

        token = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Válido",
            scopes=["crm:read"],
            expires_at=timezone.now() + timedelta(days=30),
        )
        resultado = _resolve_token(str(token.token))
        assert resultado is not None
        assert resultado["empresa_id"] == str(empresa_a.id_empresa)
        assert "crm:read" in resultado["scopes"]

    def test_require_scope_lanza_error_sin_scope(self, db):
        from apps.core.mcp_server import _require_scope

        context = {"scopes": ["crm:read"], "empresa_id": "x", "actor_id": "y", "tenant_id": "z"}
        with pytest.raises(PermissionError):
            _require_scope(context, "ventas:write")

    def test_require_scope_pasa_con_scope_correcto(self, db):
        from apps.core.mcp_server import _require_scope

        context = {"scopes": ["crm:read"], "empresa_id": "x", "actor_id": "y", "tenant_id": "z"}
        # No debe lanzar excepción
        _require_scope(context, "crm:read")

    def test_require_scope_pasa_con_wildcard(self, db):
        from apps.core.mcp_server import _require_scope

        context = {"scopes": ["*"], "empresa_id": "x", "actor_id": "y", "tenant_id": "z"}
        _require_scope(context, "ventas:write")
        _require_scope(context, "cualquier:cosa")

    def test_require_scope_lanza_error_con_none(self, db):
        from apps.core.mcp_server import _require_scope

        with pytest.raises(PermissionError, match="inválido"):
            _require_scope(None, "crm:read")
