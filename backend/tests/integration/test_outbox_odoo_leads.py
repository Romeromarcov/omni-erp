"""Cobertura integral PR-29 (Plan 07 — Omni Connect S7 + S8 + S9).

Cubre:
- S7: Modelo ``integration_hub.EventoOutbox`` (``clean()``, unicidad, sin NUL),
  PostgreSQL RLS forzada (aislamiento Empresa A vs B y ``WITH CHECK``) y
  publicación atómica desde Connect/CRM (captura pública, creación manual,
  cambio de etapa, conversión y anonimización sin PII + rollback atómico).
- S8: Dispatcher ``despachar_lote_outbox`` + tarea Celery ``integration_hub.despachar_outbox``
  + Beat schedule: descubrimiento acotado con ``rls_bypass()``, aislamiento por
  tenant con ``rls_tenant_context()``, bloqueo ``select_for_update(skip_locked=True)``,
  no-op limpio sin destino opt-in, backoff exponencial, paso a ``DLQ`` y
  sanitización de errores sin fugas de credenciales/SQL.
- S9: ``OdooXMLRPCClient`` (``crear_lead_crm`` / ``actualizar_lead_crm`` /
  ``buscar_lead_crm_por_tag``) y ``OdooConnector.push_lead``: opt-in estricto
  ``empujar_connect_leads=True``, credenciales de escritura fail-closed
  (``write_user`` / ``write_api_key``), escape HTML en ``description``,
  idempotencia create→update vía ``EntidadSincronizada``, propagación de
  anonimización sin crear registro nuevo y garantía estricta de que NUNCA
  se invoca ``res.partner`` (solo ``crm.lead``).
- REST API (``/api/integration-hub/outbox/`` + ``reintentar/``) y paridad MCP
  (``hub_listar_outbox`` / ``hub_reintentar_outbox``).

Regla de seguridad: CERO tráfico real y CERO referencias a Odoo producción; solo
hosts ``https://odoo-test.example.invalid`` y llaves dummy ``ci-only-dummy-key-*``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch
from xmlrpc.client import Fault

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.connect.services import TEXTO_CONSENTIMIENTO_DEFAULT, capturar_lead_publico
from apps.core import mcp_server, rls
from apps.core.models import CapabilityToken
from apps.crm.models import Etapa, Lead
from apps.crm.services import crear_lead_crm, mover_lead_etapa
from apps.crm.services_conversion import anonimizar_lead, convertir_lead_a_cliente
from apps.integration_hub import mcp as hub_mcp
from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    ConnectorDataError,
    ConnectorNotSupportedError,
)
from apps.integration_hub.connectors.odoo.client import (
    OdooAuthError,
    OdooCallError,
    OdooXMLRPCClient,
    sanitizar_error_odoo,
)
from apps.integration_hub.connectors.odoo.connector import OdooConnector
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    EventoOutbox,
)
from apps.integration_hub.outbox import (
    ENTIDAD_CRM_LEAD,
    EVENTO_CRM_LEAD_ACTUALIZADO,
    EVENTO_CRM_LEAD_ANONIMIZADO,
    EVENTO_CRM_LEAD_CAPTURADO,
    EVENTO_CRM_LEAD_CONVERTIDO,
    EVENTO_CRM_LEAD_ETAPA_CAMBIADA,
    OUTBOX_BACKOFF_MAX_SEGUNDOS,
    OutboxError,
    _secretos_instancias,
    _try_advisory_lock_entidad,
    calcular_backoff_segundos,
    construir_clave_idempotencia_unica,
    despachar_lote_outbox,
    encolar_evento_outbox,
    reintentar_evento_outbox,
    sanitizar_error_outbox,
)
from apps.integration_hub.serializers import ConectorInstanciaSerializer
from apps.integration_hub.tasks import despachar_outbox
from apps.integration_hub.views import EventoOutboxViewSet
from tests.connect.builders import consentimiento, crear_etapa, crear_lead, crear_perfil, crear_pipeline, crear_tarjeta

pytestmark = [pytest.mark.django_db]

BASE_HUB = "/api/integration-hub"
TEST_ODOO_HOST = "https://odoo-test.example.invalid"
DUMMY_READ_KEY = "ci-only-dummy-key-read-001"
DUMMY_WRITE_KEY = "ci-only-dummy-key-write-001"


def _api_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _mcp_token(empresa, scopes: list[str], *, creado_por=None) -> str:
    tok = CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-outbox-s7-s9",
        scopes=scopes,
        activo=True,
        creado_por=creado_por,
    )
    return str(tok.token)


@pytest.fixture
def proveedor_odoo(db):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo",
        defaults={
            "nombre": "Odoo",
            "estado": "activo",
            "capacidades": ["contactos", "productos", "pagos", "gestiones_cobranza"],
        },
    )
    return prov


def _crear_instancia_odoo(empresa, proveedor, **cfg_overrides) -> ConectorInstancia:
    cfg = {
        "host": TEST_ODOO_HOST,
        "db": "odoo_test_db",
        "user": "reader@example.invalid",
        "api_key": DUMMY_READ_KEY,
        "write_user": "writer@example.invalid",
        "write_api_key": DUMMY_WRITE_KEY,
        "empujar_connect_leads": True,
    }
    cfg.update(cfg_overrides)
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        nombre=f"Odoo Connect {uuid.uuid4().hex[:6]}",
        estado="activo",
        configuracion=cfg,
        entidades_activas=["contactos"],
    )


class _RecordingOdooClient(OdooXMLRPCClient):
    """Cliente Odoo XML-RPC simulado que registra toda llamada ``(model, method, domain, kwargs)``."""

    def __init__(self, *, write_enabled: bool = True, search_result: list[int] | None = None, next_id: int = 501):
        self._host = TEST_ODOO_HOST
        self._db = "odoo_test_db"
        self._user = "writer@example.invalid"
        self._api_key = DUMMY_WRITE_KEY
        self._write_user = "writer@example.invalid" if write_enabled else ""
        self._write_api_key = DUMMY_WRITE_KEY if write_enabled else ""
        self._write_enabled = write_enabled
        self._write_uid = 99 if write_enabled else None
        self.uid = 99
        self._models = None
        self._fields_cache = {}
        self._next_id = next_id
        self._search_result = list(search_result or [])
        self.calls: list[tuple[str, str, list | None, dict | None]] = []

    def ping(self) -> bool:
        return True

    def call(self, model: str, method: str, domain=None, kwargs=None):
        self.calls.append((model, method, domain, kwargs))
        if method == "search":
            return list(self._search_result)
        if method == "create":
            created = self._next_id
            self._next_id += 1
            return created
        if method == "write":
            return True
        raise AssertionError(f"Llamada inesperada: {model}.{method}")


# ── 1. Modelo EventoOutbox + PostgreSQL RLS (S7) ─────────────────────────────


class TestEventoOutboxModeloYRls:
    def test_clean_valida_campos_y_rechaza_nul_y_formato_invalido(self, empresa_a):
        eid = uuid.uuid4()
        valido = EventoOutbox(
            id_empresa=empresa_a,
            tipo_evento="  crm.lead.capturado  ",
            entidad_tipo="  crm.Lead  ",
            entidad_id=eid,
            clave_idempotencia="  clave-ok-1  ",
            payload={"lead_id": str(eid), "lista": ["ok"]},
            ultimo_error="",
            max_intentos=5,
        )
        valido.full_clean()
        valido.save()
        assert valido.tipo_evento == "crm.lead.capturado"
        assert valido.entidad_tipo == "crm.Lead"
        assert valido.clave_idempotencia == "clave-ok-1"
        assert "crm.lead.capturado" in str(valido)
        assert "crm_lead" in dict(EntidadSincronizada.TIPO_CHOICES)

        # Validaciones de error: formato inválido, vacíos, max_intentos=0, payload no dict
        invalido = EventoOutbox(
            id_empresa=empresa_a,
            tipo_evento="MAYUSCULAS INVALIDAS",
            entidad_tipo="   ",
            entidad_id=eid,
            clave_idempotencia="   ",
            payload=["no-dict"],  # type: ignore[arg-type]
            max_intentos=0,
        )
        with pytest.raises(DjangoValidationError) as exc_inv:
            invalido.full_clean()
        assert {"tipo_evento", "entidad_tipo", "clave_idempotencia", "payload", "max_intentos"} <= set(
            exc_inv.value.message_dict
        )

        # Bytes NUL en texto y payload anidado + clave > 120
        con_nul = EventoOutbox(
            id_empresa=empresa_a,
            tipo_evento="crm.lead\x00.capturado",
            entidad_tipo="crm\x00.Lead",
            entidad_id=eid,
            clave_idempotencia="clave\x00bad",
            payload={"ok": [{"nested": "malo\x00"}]},
            ultimo_error="err\x00or",
        )
        with pytest.raises(DjangoValidationError) as exc_nul:
            con_nul.full_clean()
        assert {"tipo_evento", "entidad_tipo", "clave_idempotencia", "payload", "ultimo_error"} <= set(
            exc_nul.value.message_dict
        )

        # Clave NUL en dict key del payload y longitud > 120
        con_key_nul = EventoOutbox(
            id_empresa=empresa_a,
            tipo_evento="crm.lead.capturado",
            entidad_tipo="crm.Lead",
            entidad_id=eid,
            clave_idempotencia="x" * 121,
            payload={"k\x00": "v"},
        )
        with pytest.raises(DjangoValidationError) as exc_key:
            con_key_nul.full_clean()
        assert {"clave_idempotencia", "payload"} <= set(exc_key.value.message_dict)

    @pytest.mark.tenant
    @override_settings(RLS_ENABLED=True)
    def test_rls_integration_hub_evento_outbox_aislamiento_y_with_check(self, empresa_a, empresa_b, rls_test_role):
        assert rls.RLS_TABLES["integration_hub_evento_outbox"] == "id_empresa_id"

        with rls.rls_bypass():
            ev_a = encolar_evento_outbox(
                empresa_a,
                tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
                entidad_tipo=ENTIDAD_CRM_LEAD,
                entidad_id=uuid.uuid4(),
                payload={"origen": "A"},
                clave_idempotencia="rls-misma-clave",
            )
            ev_b = encolar_evento_outbox(
                empresa_b,
                tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
                entidad_tipo=ENTIDAD_CRM_LEAD,
                entidad_id=uuid.uuid4(),
                payload={"origen": "B"},
                clave_idempotencia="rls-misma-clave",
            )

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            rls.apply_system_default()
            assert EventoOutbox.objects.count() == 0

            with rls.rls_tenant_context([empresa_a.pk]):
                assert set(EventoOutbox.objects.values_list("pk", flat=True)) == {ev_a.pk}
                with pytest.raises((IntegrityError, ProgrammingError)):
                    with transaction.atomic():
                        EventoOutbox.objects.create(
                            id_empresa=empresa_b,
                            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
                            entidad_tipo=ENTIDAD_CRM_LEAD,
                            entidad_id=uuid.uuid4(),
                            clave_idempotencia="rls-cross-write",
                        )

            with rls.rls_tenant_context([empresa_b.pk]):
                assert set(EventoOutbox.objects.values_list("pk", flat=True)) == {ev_b.pk}

            assert rls._get_current_context() == ("off", "")
            assert EventoOutbox.objects.count() == 0
        finally:
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")
            rls.apply_system_default()


# ── 2. Publicación atómica, idempotencia y rollback (S7) ─────────────────────


class TestPublicacionAtomicaOutbox:
    def test_encolar_idempotencia_auto_clave_y_race_integrity_error(self, empresa_a):
        eid = uuid.uuid4()
        ev1 = encolar_evento_outbox(
            empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=eid,
            payload={"lead_id": str(eid)},
            clave_idempotencia=f"idem:{eid}",
        )
        ev2 = encolar_evento_outbox(
            empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=eid,
            payload={"lead_id": str(eid)},
            clave_idempotencia=f"idem:{eid}",
        )
        assert ev1.pk == ev2.pk
        assert EventoOutbox.objects.filter(id_empresa=empresa_a, clave_idempotencia=f"idem:{eid}").count() == 1

        # Sin clave_idempotencia genera una clave válida automáticamente sin truncar uuid7().hex
        ev_auto = encolar_evento_outbox(
            empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=str(eid),
            payload={},
        )
        assert ev_auto.clave_idempotencia.startswith(f"{EVENTO_CRM_LEAD_CAPTURADO}:")
        clave_larga = construir_clave_idempotencia_unica("a" * 110)
        assert len(clave_larga) == 120
        assert len(clave_larga.rsplit(":", 1)[1]) == 32

        # NUL en tipo_evento / entidad_tipo / clave_idempotencia se rechaza ANTES de consultar SQL
        with patch.object(EventoOutbox.objects, "filter") as mock_filter_nul:
            with pytest.raises(DjangoValidationError) as exc_nul_pre:
                encolar_evento_outbox(
                    empresa_a,
                    tipo_evento="crm.lead\x00.capturado",
                    entidad_tipo="crm\x00.Lead",
                    entidad_id=eid,
                    clave_idempotencia="clave\x00mala",
                )
        assert {"tipo_evento", "entidad_tipo", "clave_idempotencia"} <= set(exc_nul_pre.value.message_dict)
        mock_filter_nul.assert_not_called()

        # UUID inválido o con NUL lanza ValidationError
        with pytest.raises(DjangoValidationError):
            encolar_evento_outbox(
                empresa_a,
                tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
                entidad_tipo=ENTIDAD_CRM_LEAD,
                entidad_id="no-es-uuid",
            )
        with pytest.raises(DjangoValidationError):
            encolar_evento_outbox(
                empresa_a,
                tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
                entidad_tipo=ENTIDAD_CRM_LEAD,
                entidad_id=f"{eid}\x00",
            )

        # Recuperación ante IntegrityError concurrente (clave nueva pasa full_clean y colisiona en save)
        orig_filter = EventoOutbox.objects.filter
        race_key = f"race:{uuid.uuid4()}"

        def _fake_filter(*args, **kwargs):
            if kwargs.get("clave_idempotencia") == race_key:
                # 1ra consulta (antes de save) devuelve None; 2da consulta (en except IntegrityError) devuelve ev1
                _fake_filter.calls += 1
                if _fake_filter.calls == 1:
                    return MagicMock(first=MagicMock(return_value=None))
                return MagicMock(first=MagicMock(return_value=ev1))
            return orig_filter(*args, **kwargs)

        _fake_filter.calls = 0
        with (
            patch.object(EventoOutbox.objects, "filter", side_effect=_fake_filter),
            patch.object(EventoOutbox, "save", side_effect=IntegrityError("duplicate key")),
        ):
            ev_race = encolar_evento_outbox(
                empresa_a,
                tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
                entidad_tipo=ENTIDAD_CRM_LEAD,
                entidad_id=eid,
                clave_idempotencia=race_key,
            )
        assert ev_race.pk == ev1.pk

    def test_integracion_connect_crm_eventos_y_rollback_atomico(self, empresa_a, user_a):
        # 1. Captura pública (apps.connect.services.capturar_lead_publico)
        perfil = crear_perfil(empresa_a, usuario=user_a, slug="vendedor-outbox")
        tarjeta = crear_tarjeta(empresa_a, perfil=perfil, estado="ACTIVA")
        res_pub = capturar_lead_publico(
            slug=perfil.slug,
            uid=tarjeta.uid_chip,
            datos={
                "nombre": "Carla",
                "apellido": "Rojas",
                "empresa_nombre": "Lubricantes del Norte",
                "email": "carla.rojas@ejemplo.test",
                "telefono": "0414-5551122",
                "mensaje": "Cotización 50 tambores",
                "consentimiento_aceptado": True,
                "consentimiento_texto": TEXTO_CONSENTIMIENTO_DEFAULT,
            },
        )
        lead_pub_id = uuid.UUID(res_pub["lead_id"])
        ev_pub = EventoOutbox.objects.get(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_id=lead_pub_id,
        )
        assert ev_pub.entidad_tipo == ENTIDAD_CRM_LEAD
        assert ev_pub.estado == EventoOutbox.Estado.PENDIENTE
        assert ev_pub.payload["fuente"] == Lead.Fuente.NFC

        # 2. Creación manual (apps.crm.services.crear_lead_crm) + mover_lead_etapa + convertir + anonimizar
        lead_man = crear_lead_crm(
            empresa=empresa_a,
            nombre="Pedro",
            apellido="Gómez",
            empresa_nombre="Talleres Sur",
            email="pedro.gomez@ejemplo.test",
            telefono="0412-8889900",
            mensaje="Interesado en aceite 20W50",
            propietario=user_a,
        )
        assert (
            EventoOutbox.objects.filter(
                id_empresa=empresa_a,
                tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
                entidad_id=lead_man.pk,
            ).count()
            == 1
        )

        etapa_contactado = Etapa.objects.get(
            id_empresa=empresa_a,
            pipeline=lead_man.pipeline,
            nombre="Contactado",
        )
        mover_lead_etapa(lead_man, etapa_contactado, user_a)
        ev_etapa = EventoOutbox.objects.get(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_ETAPA_CAMBIADA,
            entidad_id=lead_man.pk,
        )
        assert ev_etapa.payload["etapa_id"] == str(etapa_contactado.pk)
        assert ev_etapa.payload["etapa_nombre"] == "Contactado"

        # Conversión idempotente (dos llamadas -> un solo EventoOutbox convertido)
        conv_1 = convertir_lead_a_cliente(
            lead_man.pk,
            user_a,
            {"razon_social": "Talleres Sur C.A.", "rif": "J-401234567"},
        )
        conv_2 = convertir_lead_a_cliente(
            lead_man.pk,
            user_a,
            {"razon_social": "Talleres Sur C.A.", "rif": "J-401234567"},
        )
        assert conv_1["ya_convertido"] is False
        assert conv_2["ya_convertido"] is True
        ev_conv = EventoOutbox.objects.get(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CONVERTIDO,
            entidad_id=lead_man.pk,
        )
        assert ev_conv.payload["cliente_id"] == str(conv_1["cliente"].pk)

        # Anonimización -> payload estrictamente sin PII
        anonimizar_lead(
            lead_pub_id,
            user_a,
            request_meta={"motivo": "Solicitud titular Carla Rojas carla.rojas@ejemplo.test"},
        )
        ev_anon = EventoOutbox.objects.get(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_ANONIMIZADO,
            entidad_id=lead_pub_id,
        )
        payload_dump = json.dumps(ev_anon.payload, ensure_ascii=False).lower()
        assert ev_anon.payload == {"lead_id": str(lead_pub_id), "anonimizado": True}
        for pii in ("carla", "rojas", "0414", "5551122", "lubricantes", "tambores", "solicitud"):
            assert pii not in payload_dump

        # 3. Rollback atómico: si la transacción aborta tras crear_lead_crm, no persiste ni Lead ni Outbox
        total_leads_antes = Lead.objects.filter(id_empresa=empresa_a).count()
        total_outbox_antes = EventoOutbox.objects.filter(id_empresa=empresa_a).count()
        with pytest.raises(RuntimeError, match="fallo_transaccion"):
            with transaction.atomic():
                crear_lead_crm(
                    empresa=empresa_a,
                    nombre="Lead Rollback",
                    propietario=user_a,
                )
                raise RuntimeError("fallo_transaccion")
        assert Lead.objects.filter(id_empresa=empresa_a).count() == total_leads_antes
        assert EventoOutbox.objects.filter(id_empresa=empresa_a).count() == total_outbox_antes


# ── 3. OdooXMLRPCClient & OdooConnector.push_lead (S9) ───────────────────────


class TestOdooClientYConnectorPushLead:
    def test_base_connector_push_lead_no_soportado(self):
        class DummyConnector(BaseConnector):
            PROVIDER_NAME = "Dummy"

            def test_connection(self):  # pragma: no cover
                raise NotImplementedError

            def get_version_info(self):  # pragma: no cover
                raise NotImplementedError

        dummy = DummyConnector.__new__(DummyConnector)
        with pytest.raises(ConnectorNotSupportedError):
            dummy.push_lead({})

    def test_odoo_client_fail_closed_y_validaciones_crm_lead(self):
        # Asimetría en __init__ lanza OdooAuthError
        with pytest.raises(OdooAuthError, match="asimétrica"):
            OdooXMLRPCClient(
                TEST_ODOO_HOST,
                "test_db",
                "reader@example.invalid",
                DUMMY_READ_KEY,
                write_user="writer@example.invalid",
            )

        # Cliente sin _models autenticado -> fail-closed
        cli_sin_models = OdooXMLRPCClient.__new__(OdooXMLRPCClient)
        cli_sin_models._models = None
        with pytest.raises(OdooCallError, match="no autenticado"):
            cli_sin_models.call("crm.lead", "search", [[]])

        # Cliente sin modo escritura (read-only) -> fail-closed
        cli_ro = _RecordingOdooClient(write_enabled=False)
        with pytest.raises(OdooCallError, match="Modo escritura deshabilitado"):
            cli_ro.crear_lead_crm({"name": "Lead RO"})
        with pytest.raises(OdooCallError, match="Modo escritura deshabilitado"):
            cli_ro.actualizar_lead_crm(10, {"name": "Lead RO"})
        assert cli_ro.calls == []

        # Validaciones de _preparar_vals_lead_crm: solo crm.lead, prohibido partner_id, sin NUL, escape HTML
        with pytest.raises(OdooCallError, match="crm.lead"):
            OdooXMLRPCClient._preparar_vals_lead_crm({"name": "X"}, modelo="res.partner")
        with pytest.raises(OdooCallError, match="res.partner"):
            OdooXMLRPCClient._preparar_vals_lead_crm({"name": "X", "partner_id": 5})
        with pytest.raises(OdooCallError, match="no vacío"):
            OdooXMLRPCClient._preparar_vals_lead_crm({})
        with pytest.raises(OdooCallError, match="caracteres inválidos"):
            OdooXMLRPCClient._preparar_vals_lead_crm({"name": "Mal\x00o"})
        with pytest.raises(OdooCallError, match="No hay campos válidos"):
            OdooXMLRPCClient._preparar_vals_lead_crm({"name": None})

        cli_rw = _RecordingOdooClient(write_enabled=True, next_id=777)
        with pytest.raises(OdooCallError, match="entero positivo"):
            cli_rw.actualizar_lead_crm(0, {"name": "X"})
        with pytest.raises(OdooCallError, match="entero positivo"):
            cli_rw.actualizar_lead_crm(True, {"name": "X"})  # type: ignore[arg-type]

        created_id = cli_rw.crear_lead_crm(
            {
                "name": "Lead XSS",
                "email_from": None,
                "phone": False,
                "description": '<script>alert("xss")</script> & notas',
            }
        )
        assert created_id == 777
        assert cli_rw.calls[-1][0] == "crm.lead"
        assert cli_rw.calls[-1][1] == "create"
        sent_vals = cli_rw.calls[-1][2][0]
        assert "email_from" not in sent_vals
        assert sent_vals["phone"] is False
        assert sent_vals["description"] == "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt; &amp; notas"
        assert all(call[0] == "crm.lead" for call in cli_rw.calls)
        assert all(call[0] != "res.partner" for call in cli_rw.calls)

        # buscar_lead_crm_por_tag
        cli_rw._search_result = [888]
        assert cli_rw.buscar_lead_crm_por_tag("[OMNI-LEAD:abc]") == 888
        assert cli_rw.calls[-1][0] == "crm.lead"
        cli_rw._search_result = []
        assert cli_rw.buscar_lead_crm_por_tag("[OMNI-LEAD:missing]") is None
        assert cli_rw.buscar_lead_crm_por_tag("bad\x00tag") is None

    def test_odoo_client_write_creds_distintas_autentica_y_sanitiza_errores(self):
        mock_common_read = MagicMock()
        mock_common_read.version.return_value = {"server_version": "18.0"}
        mock_common_read.authenticate.return_value = 11

        mock_models = MagicMock()
        mock_models.execute_kw.side_effect = [
            901,  # create crm.lead OK
            Fault(1, f"Fallo con {DUMMY_WRITE_KEY} y api_key={DUMMY_READ_KEY}"),
            RuntimeError(f"Socket timeout {DUMMY_WRITE_KEY}"),
        ]

        mock_common_write = MagicMock()
        mock_common_write.authenticate.return_value = 22

        with patch(
            "xmlrpc.client.ServerProxy",
            side_effect=[mock_common_read, mock_models, mock_common_write],
        ):
            cli = OdooXMLRPCClient(
                TEST_ODOO_HOST,
                "test_db",
                "reader@example.invalid",
                DUMMY_READ_KEY,
                write_user="writer@example.invalid",
                write_api_key=DUMMY_WRITE_KEY,
            )
            assert cli.crear_lead_crm({"name": "Lead Separado"}) == 901
            # Verifica que execute_kw usó uid=22, write_api_key y modelo crm.lead
            first_call = mock_models.execute_kw.call_args_list[0].args
            assert first_call[1] == 22
            assert first_call[2] == DUMMY_WRITE_KEY
            assert first_call[3] == "crm.lead"
            assert first_call[4] == "create"

            with pytest.raises(OdooCallError) as exc_fault:
                cli.actualizar_lead_crm(901, {"name": "Fail Fault"})
            assert DUMMY_WRITE_KEY not in str(exc_fault.value)
            assert DUMMY_READ_KEY not in str(exc_fault.value)

            with pytest.raises(OdooCallError) as exc_rt:
                cli.actualizar_lead_crm(901, {"name": "Fail Runtime"})
            assert DUMMY_WRITE_KEY not in str(exc_rt.value)

        # Fallo de autenticación del usuario de escritura -> OdooAuthError sanitizado
        mock_common_bad = MagicMock()
        mock_common_bad.authenticate.return_value = False
        mock_common_exc = MagicMock()
        mock_common_exc.authenticate.side_effect = RuntimeError(f"err {DUMMY_WRITE_KEY}")

        with patch("xmlrpc.client.ServerProxy", side_effect=[mock_common_read, mock_models, mock_common_bad]):
            cli2 = OdooXMLRPCClient(
                TEST_ODOO_HOST,
                "test_db",
                "reader@example.invalid",
                DUMMY_READ_KEY,
                write_user="writer@example.invalid",
                write_api_key=DUMMY_WRITE_KEY,
            )
            with pytest.raises(OdooAuthError, match="escritura"):
                cli2.crear_lead_crm({"name": "Auth Fail"})

        with patch("xmlrpc.client.ServerProxy", side_effect=[mock_common_read, mock_models, mock_common_exc]):
            cli3 = OdooXMLRPCClient(
                TEST_ODOO_HOST,
                "test_db",
                "reader@example.invalid",
                DUMMY_READ_KEY,
                write_user="writer@example.invalid",
                write_api_key=DUMMY_WRITE_KEY,
            )
            with pytest.raises(OdooAuthError) as exc_a:
                cli3.crear_lead_crm({"name": "Auth Exc"})
            assert DUMMY_WRITE_KEY not in str(exc_a.value)

    def test_push_lead_opt_in_estricto_y_fail_closed_sin_write_creds(self, empresa_a, proveedor_odoo):
        # 1. empujar_connect_leads=False o string truthy -> fail-closed
        for flag in (False, None, "true"):
            inst = _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=flag)
            with pytest.raises(ConnectorConnectionError, match="empujar_connect_leads"):
                OdooConnector(inst).push_lead({"lead_id": str(uuid.uuid4()), "nombre": "Test"})

        # 2. empujar_connect_leads=True pero sin write_user / write_api_key -> fail-closed (no cae a read creds)
        inst_no_write = _crear_instancia_odoo(empresa_a, proveedor_odoo, write_user="", write_api_key="")
        with pytest.raises(ConnectorConnectionError, match="write_user"):
            OdooConnector(inst_no_write).push_lead({"lead_id": str(uuid.uuid4()), "nombre": "Test"})

        # 3. Sin host -> ConnectorConnectionError; HTTP en DEBUG=False -> M-SEC-2 exige https://
        inst_no_host = _crear_instancia_odoo(empresa_a, proveedor_odoo, host="")
        with pytest.raises(ConnectorConnectionError, match="host"):
            OdooConnector(inst_no_host).push_lead({"lead_id": str(uuid.uuid4()), "nombre": "Test"})

        inst_http = _crear_instancia_odoo(empresa_a, proveedor_odoo, host="http://odoo-test.example.invalid")
        with override_settings(DEBUG=False):
            with pytest.raises(ConnectorConnectionError, match="https://"):
                OdooConnector(inst_http).push_lead({"lead_id": str(uuid.uuid4()), "nombre": "Test"})

        # 4. Error de autenticación Odoo -> ConnectorConnectionError sanitizado (sin secret)
        inst_ok = _crear_instancia_odoo(empresa_a, proveedor_odoo)
        with patch(
            "apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient",
            side_effect=OdooAuthError(f"bad auth {DUMMY_WRITE_KEY}"),
        ):
            with pytest.raises(ConnectorConnectionError) as exc_auth:
                OdooConnector(inst_ok).push_lead({"lead_id": str(uuid.uuid4()), "nombre": "Test"})
        assert DUMMY_WRITE_KEY not in str(exc_auth.value)

        # 5. Reconexión automática cuando ping() falla o lanza excepción en _connect_write_client
        conn_rec = OdooConnector(inst_ok)
        cli_muerto = MagicMock()
        cli_muerto.ping.side_effect = RuntimeError("socket cerrado")
        cli_nuevo = _RecordingOdooClient(write_enabled=True, next_id=950)
        conn_rec._connect_write_client = cli_muerto
        with patch(
            "apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient",
            return_value=cli_nuevo,
        ) as mock_cls:
            res_rec = conn_rec.push_lead({"lead_id": str(uuid.uuid4()), "nombre": "Reconectado"})
        assert res_rec["odoo_lead_id"] == 950
        mock_cls.assert_called_once()

        # OdooAuthError durante la ejecución de push_lead -> ConnectorConnectionError sanitizado
        with patch.object(cli_nuevo, "crear_lead_crm", side_effect=OdooAuthError(f"expired {DUMMY_WRITE_KEY}")):
            with pytest.raises(ConnectorConnectionError) as exc_auth_push:
                conn_rec.push_lead({"lead_id": str(uuid.uuid4()), "nombre": "Token Expirado"})
        assert DUMMY_WRITE_KEY not in str(exc_auth_push.value)

    def test_push_lead_ciclo_completo_idempotencia_html_etapas_anonimizacion_y_cero_res_partner(
        self, empresa_a, user_a, proveedor_odoo
    ):
        pipe = crear_pipeline(empresa_a, nombre="Ventas Connect")
        etapa_nuevo = crear_etapa(empresa_a, pipe, nombre="Nuevo", orden=1, tipo=Etapa.Tipo.ABIERTA)
        etapa_calif = crear_etapa(empresa_a, pipe, nombre="Calificado", orden=2, tipo=Etapa.Tipo.ABIERTA)
        etapa_ganado = crear_etapa(empresa_a, pipe, nombre="Ganado", orden=3, tipo=Etapa.Tipo.GANADA)

        inst = _crear_instancia_odoo(
            empresa_a,
            proveedor_odoo,
            mapa_etapas_odoo={
                str(etapa_nuevo.pk): 10,
                "Calificado": 20,
                str(etapa_ganado.pk): 30,
            },
        )
        lead = crear_lead(
            empresa_a,
            pipeline=pipe,
            etapa=etapa_nuevo,
            propietario=user_a,
            nombre="María",
            apellido="Díaz",
            empresa_nombre="Ferretería Central",
            email="maria@central.example.invalid",
            telefono="+584141112233",
            mensaje="<b>Urgente</b> <script>alert(1)</script>",
            fuente=Lead.Fuente.NFC,
            **consentimiento(),
        )

        cli = _RecordingOdooClient(write_enabled=True, next_id=601)
        conn = OdooConnector(inst)
        conn._connect_write_client = cli

        # 1. Primer evento (capturado) -> CREATE en crm.lead + registro en EntidadSincronizada
        ev_cap = encolar_evento_outbox(
            empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead.pk,
            payload={"lead_id": str(lead.pk)},
            clave_idempotencia=f"cap:{lead.pk}",
        )
        res_create = conn.push_lead(ev_cap)
        assert res_create == {"accion": "creado", "odoo_lead_id": 601, "lead_id": str(lead.pk)}

        mapeo = EntidadSincronizada.objects.get(
            id_instancia=inst,
            tipo_entidad="crm_lead",
            id_omni=str(lead.pk),
        )
        assert mapeo.id_externo == "601"
        assert mapeo.modelo_omni == "apps.crm.models.Lead"

        create_call = next(c for c in cli.calls if c[1] == "create")
        assert create_call[0] == "crm.lead"
        vals_creados = create_call[2][0]
        assert vals_creados["name"] == "María Díaz — Ferretería Central"
        assert vals_creados["contact_name"] == "María Díaz"
        assert vals_creados["partner_name"] == "Ferretería Central"
        assert vals_creados["email_from"] == "maria@central.example.invalid"
        assert vals_creados["stage_id"] == 10
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in vals_creados["description"]
        assert "<script>" not in vals_creados["description"]

        # 2. Segundo evento (etapa_cambiada) -> UPDATE mismo ID 601 (SIN duplicar create)
        lead.etapa = etapa_calif
        lead.save(update_fields=["etapa"])
        ev_etapa = encolar_evento_outbox(
            empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_ETAPA_CAMBIADA,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead.pk,
            payload={"lead_id": str(lead.pk), "etapa_id": str(etapa_calif.pk)},
            clave_idempotencia=f"etapa:{lead.pk}",
        )
        res_update = conn.push_lead(ev_etapa)
        assert res_update == {"accion": "actualizado", "odoo_lead_id": 601, "lead_id": str(lead.pk)}
        assert sum(1 for c in cli.calls if c[1] == "create") == 1
        write_call = cli.calls[-1]
        assert write_call[0] == "crm.lead"
        assert write_call[1] == "write"
        assert write_call[2][0] == [601]
        assert write_call[2][1]["stage_id"] == 20

        # 3. Conversión -> UPDATE mismo ID 601
        res_conv = conn.push_lead(
            {
                "tipo_evento": EVENTO_CRM_LEAD_CONVERTIDO,
                "lead_id": str(lead.pk),
                "cliente_id": str(uuid.uuid4()),
            }
        )
        assert res_conv["accion"] == "actualizado"
        assert res_conv["odoo_lead_id"] == 601
        assert "Convertido a cliente Omni" in cli.calls[-1][2][1]["description"]

        # 4. Anonimización sobre lead YA sincronizado -> sobrescribe PII en ID 601
        ev_anon = encolar_evento_outbox(
            empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_ANONIMIZADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead.pk,
            payload={"lead_id": str(lead.pk), "anonimizado": True},
            clave_idempotencia=f"anon:{lead.pk}",
        )
        res_anon = conn.push_lead(ev_anon)
        assert res_anon == {"accion": "anonimizado", "odoo_lead_id": 601, "lead_id": str(lead.pk)}
        anon_vals = cli.calls[-1][2][1]
        assert anon_vals == {
            "name": "Contacto anonimizado",
            "contact_name": "",
            "email_from": False,
            "phone": False,
            "partner_name": False,
            "description": "Anonimizado por solicitud de privacidad",
        }
        mapeo.refresh_from_db()
        assert mapeo.metadatos["anonimizado"] is True

        # 5. Anonimización sobre lead NUNCA sincronizado (ni en BD ni en Odoo) -> solo lectura search, cero create/write
        calls_antes = len(cli.calls)
        lead_nunca_sync = uuid.uuid4()
        cli._search_result = []
        res_omit = conn.push_lead(
            {
                "tipo_evento": EVENTO_CRM_LEAD_ANONIMIZADO,
                "lead_id": str(lead_nunca_sync),
                "anonimizado": True,
            }
        )
        assert res_omit == {
            "accion": "omitido",
            "odoo_lead_id": None,
            "lead_id": str(lead_nunca_sync),
            "motivo": "lead_no_sincronizado",
        }
        nuevas_calls_omit = cli.calls[calls_antes:]
        assert [(c[0], c[1]) for c in nuevas_calls_omit] == [("crm.lead", "search")]

        # 5b. Anonimización con fallo parcial previo (existe en Odoo vía tag, sin EntidadSincronizada local)
        calls_antes_tag = len(cli.calls)
        lead_huerfano_odoo = uuid.uuid4()
        cli._search_result = [712]
        res_anon_tag = conn.push_lead(
            {
                "tipo_evento": EVENTO_CRM_LEAD_ANONIMIZADO,
                "lead_id": str(lead_huerfano_odoo),
                "anonimizado": True,
            }
        )
        assert res_anon_tag == {
            "accion": "anonimizado",
            "odoo_lead_id": 712,
            "lead_id": str(lead_huerfano_odoo),
        }
        nuevas_calls_tag = cli.calls[calls_antes_tag:]
        assert [(c[0], c[1]) for c in nuevas_calls_tag] == [("crm.lead", "search"), ("crm.lead", "write")]
        assert nuevas_calls_tag[1][2][0] == [712]
        assert nuevas_calls_tag[1][2][1]["email_from"] is False
        mapeo_anon_rec = EntidadSincronizada.objects.get(
            id_instancia=inst,
            tipo_entidad="crm_lead",
            id_externo="712",
            id_omni=str(lead_huerfano_odoo),
        )
        assert mapeo_anon_rec.metadatos["anonimizado"] is True

        # 6. Recuperación idempotente vía buscar_lead_crm_por_tag (p. ej. tras timeout sin guardar EntidadSincronizada)
        lead_recuperado_id = str(uuid.uuid4())
        cli._search_result = [777]
        res_rec = conn.push_lead(
            {
                "tipo_evento": EVENTO_CRM_LEAD_CAPTURADO,
                "lead_id": lead_recuperado_id,
                "nombre": "Lead Recuperado",
                "email": "rec@example.invalid",
            }
        )
        assert res_rec == {"accion": "actualizado", "odoo_lead_id": 777, "lead_id": lead_recuperado_id}
        assert EntidadSincronizada.objects.filter(
            id_instancia=inst,
            tipo_entidad="crm_lead",
            id_externo="777",
            id_omni=lead_recuperado_id,
        ).exists()

        # 7. Validación de entradas inválidas y errores OdooCallError -> ConnectorDataError
        with pytest.raises(ConnectorDataError):
            conn.push_lead("invalido")
        with pytest.raises(ConnectorDataError):
            conn.push_lead({"nombre": "Sin ID"})

        with patch.object(cli, "actualizar_lead_crm", side_effect=OdooCallError(f"boom {DUMMY_WRITE_KEY}")):
            with pytest.raises(ConnectorDataError) as exc_data:
                conn.push_lead({"lead_id": lead_recuperado_id, "nombre": "Fallo"})
        assert DUMMY_WRITE_KEY not in str(exc_data.value)

        # ASERCIÓN INVIOLABLE: NUNCA se invoca res.partner en todo el flujo Connect
        modelos_invocados = {c[0] for c in cli.calls}
        assert modelos_invocados == {"crm.lead"}
        assert "res.partner" not in modelos_invocados


# ── 4. Dispatcher Celery: skip_locked, no-op, backoff exponencial y DLQ (S8) ─


class TestDispatcherOutboxCelery:
    def test_backoff_exponencial_y_sanitizacion_error(self):
        assert calcular_backoff_segundos(1) == 60
        assert calcular_backoff_segundos(2) == 120
        assert calcular_backoff_segundos(3) == 240
        assert calcular_backoff_segundos(4) == 480
        assert calcular_backoff_segundos(10) == OUTBOX_BACKOFF_MAX_SEGUNDOS

        assert DUMMY_WRITE_KEY not in sanitizar_error_outbox(
            f"Fallo conectando con {DUMMY_WRITE_KEY}",
            secrets=(DUMMY_WRITE_KEY,),
        )
        # Enmascaramiento de secretos entrecomillados (JSON/key=val) y tokens Bearer (R-CODE-8)
        san_quoted = sanitizar_error_odoo(
            "Error {\"api_key\": \"ci-only-dummy-key-json-1\", 'password': 'mi secreto', "
            'write_api_key="ci-only-dummy-key-q2"} Authorization: Bearer ci-only-dummy-key-bearer-1'
        )
        for filtrado in (
            "ci-only-dummy-key-json-1",
            "mi secreto",
            "ci-only-dummy-key-q2",
            "ci-only-dummy-key-bearer-1",
        ):
            assert filtrado not in san_quoted
        assert "Bearer ***" in san_quoted
        assert (
            sanitizar_error_outbox("SELECT * FROM usuarios WHERE password=abc") == "Error despachando evento outbox."
        )
        assert sanitizar_error_outbox("err\x00limpio") == "errlimpio"
        assert "hub-despachar-outbox" in settings.CELERY_BEAT_SCHEDULE
        assert settings.CELERY_BEAT_SCHEDULE["hub-despachar-outbox"]["task"] == "integration_hub.despachar_outbox"

    def test_noop_sin_conector_opt_in_marca_enviado_limpio(self, empresa_a, user_a, proveedor_odoo):
        # Conector presente pero con empujar_connect_leads=False -> no-op limpio
        _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=False)
        lead = crear_lead_crm(empresa=empresa_a, nombre="Lead Sin Opt-In", propietario=user_a)
        ev_otro = encolar_evento_outbox(
            empresa_a,
            tipo_evento="otro.modulo.evento",
            entidad_tipo="otro.Modelo",
            entidad_id=uuid.uuid4(),
            clave_idempotencia="otro-1",
        )

        res = despachar_outbox.apply(kwargs={"limite": 20}).get()
        assert res["enviados"] == 2
        assert res["sin_destino"] == 2
        assert res["fallidos"] == 0
        assert res["dlq"] == 0

        ev_lead = EventoOutbox.objects.get(entidad_id=lead.pk)
        ev_otro.refresh_from_db()
        assert ev_lead.estado == EventoOutbox.Estado.ENVIADO
        assert ev_lead.procesado_en is not None
        assert ev_otro.estado == EventoOutbox.Estado.ENVIADO

    @pytest.mark.tenant
    @override_settings(RLS_ENABLED=True)
    def test_despachar_outbox_bajo_rls_fail_closed_envia_a_odoo_aislado(
        self, empresa_a, empresa_b, user_a, user_b, proveedor_odoo, rls_test_role
    ):
        with rls.rls_bypass():
            inst_a = _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=True)
            _crear_instancia_odoo(empresa_b, proveedor_odoo, empujar_connect_leads=False)
            lead_a = crear_lead_crm(empresa=empresa_a, nombre="Lead RLS A", propietario=user_a)
            lead_b = crear_lead_crm(empresa=empresa_b, nombre="Lead RLS B", propietario=user_b)

        cli_a = _RecordingOdooClient(write_enabled=True, next_id=810)

        def _fake_get_connector(instancia):
            conn = OdooConnector(instancia)
            conn._connect_write_client = cli_a
            return conn

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            rls.apply_system_default()
            assert EventoOutbox.objects.count() == 0

            with patch.object(registry, "get_connector", side_effect=_fake_get_connector):
                res = despachar_lote_outbox(limite=50)

            assert res["enviados"] == 2
            assert res["sin_destino"] == 1  # empresa_b sin opt-in
            assert res["fallidos"] == 0
            assert rls._get_current_context() == ("off", "")
            assert EventoOutbox.objects.count() == 0

            with rls.rls_bypass():
                assert EventoOutbox.objects.get(entidad_id=lead_a.pk).estado == EventoOutbox.Estado.ENVIADO
                assert EventoOutbox.objects.get(entidad_id=lead_b.pk).estado == EventoOutbox.Estado.ENVIADO
                assert EntidadSincronizada.objects.filter(
                    id_instancia=inst_a,
                    tipo_entidad="crm_lead",
                    id_externo="810",
                    id_omni=str(lead_a.pk),
                ).exists()
            assert {c[0] for c in cli_a.calls} == {"crm.lead"}
        finally:
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")
            rls.apply_system_default()

    def test_backoff_exponencial_dlq_y_skip_locked(self, empresa_a, user_a, proveedor_odoo):
        _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=True)
        lead = crear_lead_crm(empresa=empresa_a, nombre="Lead Fallo", propietario=user_a)
        ev = EventoOutbox.objects.get(entidad_id=lead.pk)
        ev.max_intentos = 3
        ev.save(update_fields=["max_intentos"])

        fake_conn = MagicMock()
        fake_conn.push_lead.side_effect = ConnectorConnectionError(f"Timeout Odoo {DUMMY_WRITE_KEY}")

        t0 = timezone.now() + timedelta(seconds=1)
        with patch.object(registry, "get_connector", return_value=fake_conn):
            # Intento 1 -> FALLIDO, backoff 60s
            r1 = despachar_lote_outbox(ahora=t0)
            assert r1["fallidos"] == 1 and r1["dlq"] == 0
            ev.refresh_from_db()
            assert ev.estado == EventoOutbox.Estado.FALLIDO
            assert ev.intentos == 1
            assert ev.proximo_intento_en == t0 + timedelta(seconds=60)
            assert DUMMY_WRITE_KEY not in ev.ultimo_error

            # Antes del vencimiento del backoff -> no se reintenta
            r_early = despachar_lote_outbox(ahora=t0 + timedelta(seconds=30))
            assert r_early["procesados"] == 0

            # Intento 2 -> FALLIDO, backoff 120s
            t1 = t0 + timedelta(seconds=61)
            r2 = despachar_lote_outbox(ahora=t1)
            assert r2["fallidos"] == 1 and r2["dlq"] == 0
            ev.refresh_from_db()
            assert ev.estado == EventoOutbox.Estado.FALLIDO
            assert ev.intentos == 2
            assert ev.proximo_intento_en == t1 + timedelta(seconds=120)

            # Intento 3 (= max_intentos) -> DLQ
            t2 = t1 + timedelta(seconds=121)
            r3 = despachar_lote_outbox(ahora=t2)
            assert r3["dlq"] == 1 and r3["fallidos"] == 0
            ev.refresh_from_db()
            assert ev.estado == EventoOutbox.Estado.DLQ
            assert ev.intentos == 3
            assert ev.procesado_en == t2

        # Simula evento ya bloqueado por otro worker (select_for_update(skip_locked=True) retorna vacío)
        ev_lock = encolar_evento_outbox(
            empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=uuid.uuid4(),
            clave_idempotencia="lock-test-1",
        )
        qs_vacio = MagicMock()
        qs_vacio.filter.return_value.first.return_value = None
        with patch.object(EventoOutbox.objects, "select_for_update", return_value=qs_vacio) as mock_sfu:
            r_skip = despachar_lote_outbox(ahora=timezone.now() + timedelta(seconds=5))
        mock_sfu.assert_called_with(skip_locked=True)
        assert r_skip["omitidos_bloqueo"] >= 1
        ev_lock.refresh_from_db()
        assert ev_lock.estado == EventoOutbox.Estado.PENDIENTE

    def test_poison_pill_config_corrupta_no_bloquea_otro_tenant(
        self, empresa_a, empresa_b, user_a, user_b, proveedor_odoo
    ):
        inst_a = _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=True)
        inst_b = _crear_instancia_odoo(empresa_b, proveedor_odoo, empujar_connect_leads=True)
        lead_a = crear_lead_crm(empresa=empresa_a, nombre="Lead Corrupto A", propietario=user_a)
        lead_b = crear_lead_crm(empresa=empresa_b, nombre="Lead Sano B", propietario=user_b)

        ev_a = EventoOutbox.objects.get(entidad_id=lead_a.pk)
        ev_b = EventoOutbox.objects.get(entidad_id=lead_b.pk)

        cli_b = _RecordingOdooClient(write_enabled=True, next_id=915)
        orig_get_config = ConectorInstancia.get_config

        def _fake_get_config(self_inst):
            if self_inst.pk == inst_a.pk:
                return "gAAAAAB-fernet-token-corrupto-sin-descifrar"
            return orig_get_config(self_inst)

        def _fake_get_connector(instancia):
            conn = OdooConnector(instancia)
            conn._connect_write_client = cli_b
            return conn

        with (
            patch.object(ConectorInstancia, "get_config", _fake_get_config),
            patch.object(registry, "get_connector", side_effect=_fake_get_connector),
        ):
            # También cubre _secretos_instancias cuando get_config devuelve str no-dict
            assert _secretos_instancias([inst_a]) == []
            res = despachar_lote_outbox(limite=50)

        assert res["fallidos"] == 1
        assert res["enviados"] == 1
        ev_a.refresh_from_db()
        ev_b.refresh_from_db()
        assert ev_a.estado == EventoOutbox.Estado.FALLIDO
        assert ev_a.intentos == 1
        assert "Configuración inválida" in ev_a.ultimo_error
        assert ev_b.estado == EventoOutbox.Estado.ENVIADO
        assert EntidadSincronizada.objects.filter(
            id_instancia=inst_b,
            tipo_entidad="crm_lead",
            id_externo="915",
            id_omni=str(lead_b.pk),
        ).exists()

    def test_multiples_destinos_savepoint_aisla_entidad_sincronizada_del_primero(
        self, empresa_a, user_a, proveedor_odoo
    ):
        inst_1 = _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=True)
        inst_2 = _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=True)
        lead = crear_lead_crm(empresa=empresa_a, nombre="Lead Dos Destinos", propietario=user_a)
        ev = EventoOutbox.objects.get(entidad_id=lead.pk)

        cli_1 = _RecordingOdooClient(write_enabled=True, next_id=921)

        def _fake_get_connector(instancia):
            if instancia.pk == inst_1.pk:
                conn_ok = OdooConnector(instancia)
                conn_ok._connect_write_client = cli_1
                return conn_ok
            conn_fail = MagicMock()
            conn_fail.push_lead.side_effect = ConnectorConnectionError("Odoo 2 caído")
            return conn_fail

        with patch.object(registry, "get_connector", side_effect=_fake_get_connector):
            res = despachar_lote_outbox(limite=50)

        assert res["fallidos"] == 1
        ev.refresh_from_db()
        assert ev.estado == EventoOutbox.Estado.FALLIDO
        # El savepoint independiente preserva EntidadSincronizada del destino 1 aunque el destino 2 falló
        assert EntidadSincronizada.objects.filter(
            id_instancia=inst_1,
            tipo_entidad="crm_lead",
            id_externo="921",
            id_omni=str(lead.pk),
        ).exists()
        assert not EntidadSincronizada.objects.filter(id_instancia=inst_2, tipo_entidad="crm_lead").exists()

    def test_advisory_lock_por_entidad_serializa_eventos_del_mismo_lead(self, empresa_a, user_a, proveedor_odoo):
        _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=True)
        lead = crear_lead_crm(empresa=empresa_a, nombre="Lead Lock Entidad", propietario=user_a)
        ev = EventoOutbox.objects.get(entidad_id=lead.pk)

        # Cuando otro worker mantiene el advisory lock del mismo lead_id, el evento se omite sin pasar a PROCESANDO
        with patch("apps.integration_hub.outbox._try_advisory_lock_entidad", return_value=False) as mock_lock:
            res = despachar_lote_outbox(limite=20)
        mock_lock.assert_called_once_with(empresa_a.pk, ENTIDAD_CRM_LEAD, lead.pk)
        assert res["omitidos_bloqueo"] == 1
        assert res["procesados"] == 0
        ev.refresh_from_db()
        assert ev.estado == EventoOutbox.Estado.PENDIENTE

        # Ejecución real de pg_try_advisory_xact_lock + fallback vendor no-postgresql
        with transaction.atomic():
            assert _try_advisory_lock_entidad(empresa_a.pk, ENTIDAD_CRM_LEAD, lead.pk) is True
        with patch.object(connection, "vendor", "sqlite"):
            assert _try_advisory_lock_entidad(empresa_a.pk, ENTIDAD_CRM_LEAD, lead.pk) is True


# ── 5. REST API + Serializers + Paridad MCP (S7–S9) ──────────────────────────


class TestOutboxRestYMcp:
    def test_serializer_conector_valida_empujar_connect_leads_y_mapa_etapas(self, empresa_a, user_a, proveedor_odoo):
        client = _api_client(user_a)

        # Rechaza empujar_connect_leads no booleano y mapa_etapas_odoo no dict
        resp_bad_flag = client.post(
            f"{BASE_HUB}/instancias/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Odoo Bad Flag",
                "configuracion": {
                    "host": TEST_ODOO_HOST,
                    "user": "reader@example.invalid",
                    "api_key": DUMMY_READ_KEY,
                    "empujar_connect_leads": "si",
                },
            },
            format="json",
        )
        assert resp_bad_flag.status_code == 400

        # Rechaza empujar_connect_leads=True sin write_user / write_api_key (fail-fast 400 en serializer)
        resp_sin_write = client.post(
            f"{BASE_HUB}/instancias/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Odoo Sin Write Creds",
                "configuracion": {
                    "host": TEST_ODOO_HOST,
                    "user": "reader@example.invalid",
                    "api_key": DUMMY_READ_KEY,
                    "empujar_connect_leads": True,
                },
            },
            format="json",
        )
        assert resp_sin_write.status_code == 400
        assert "write_user" in str(resp_sin_write.data["configuracion"])

        resp_bad_map = client.post(
            f"{BASE_HUB}/instancias/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Odoo Bad Map",
                "configuracion": {
                    "host": TEST_ODOO_HOST,
                    "user": "reader@example.invalid",
                    "api_key": DUMMY_READ_KEY,
                    "write_user": "writer@example.invalid",
                    "write_api_key": DUMMY_WRITE_KEY,
                    "empujar_connect_leads": True,
                    "mapa_etapas_odoo": ["invalido"],
                },
            },
            format="json",
        )
        assert resp_bad_map.status_code == 400
        assert "mapa_etapas_odoo" in str(resp_bad_map.data["configuracion"])

        # Consistencia estricta is True en configuracion_publica si en BD quedó un string truthy
        inst_str_flag = _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads="true")
        assert (
            ConectorInstanciaSerializer(inst_str_flag).data["configuracion_publica"]["empujar_connect_leads"] is False
        )

        # PATCH sin enviar empujar_connect_leads conserva el valor existente (rama existente.get)
        inst_ok = _crear_instancia_odoo(empresa_a, proveedor_odoo, empujar_connect_leads=True)
        resp_patch_keep = client.patch(
            f"{BASE_HUB}/instancias/{inst_ok.pk}/",
            {"configuracion": {"host": TEST_ODOO_HOST, "user": "reader@example.invalid"}},
            format="json",
        )
        assert resp_patch_keep.status_code == 200
        assert resp_patch_keep.data["configuracion_publica"]["empujar_connect_leads"] is True

        resp_ok = client.post(
            f"{BASE_HUB}/instancias/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Odoo Connect OK",
                "configuracion": {
                    "host": TEST_ODOO_HOST,
                    "user": "reader@example.invalid",
                    "api_key": DUMMY_READ_KEY,
                    "write_user": "writer@example.invalid",
                    "write_api_key": DUMMY_WRITE_KEY,
                    "empujar_connect_leads": True,
                    "mapa_etapas_odoo": {"Nuevo": 1},
                },
            },
            format="json",
        )
        assert resp_ok.status_code == 201
        pub = resp_ok.data["configuracion_publica"]
        assert pub["empujar_connect_leads"] is True
        assert pub["tiene_write_api_key"] is True
        dumped_ok = json.dumps(resp_ok.data, default=str)
        assert DUMMY_WRITE_KEY not in dumped_ok
        assert DUMMY_READ_KEY not in dumped_ok

    def test_rest_outbox_aislamiento_filtros_solo_lectura_y_reintentar(self, empresa_a, empresa_b, user_a, user_b):
        lead_id_a = uuid.uuid4()
        ev_dlq_a = EventoOutbox.objects.create(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead_id_a,
            clave_idempotencia="rest-a-dlq",
            estado=EventoOutbox.Estado.DLQ,
            intentos=5,
            max_intentos=5,
            ultimo_error="Fallo previo",
            procesado_en=timezone.now(),
        )
        ev_env_a = EventoOutbox.objects.create(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CONVERTIDO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead_id_a,
            clave_idempotencia="rest-a-env",
            estado=EventoOutbox.Estado.ENVIADO,
        )
        ev_b = EventoOutbox.objects.create(
            id_empresa=empresa_b,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=uuid.uuid4(),
            clave_idempotencia="rest-b-dlq",
            estado=EventoOutbox.Estado.DLQ,
            intentos=5,
        )

        client_a = _api_client(user_a)
        client_b = _api_client(user_b)

        # Sin auth -> 401/403
        assert APIClient().get(f"{BASE_HUB}/outbox/").status_code in (401, 403)

        # Listado multi-tenant y filtros
        r_list = client_a.get(
            f"{BASE_HUB}/outbox/?estado=dlq&tipo_evento={EVENTO_CRM_LEAD_CAPTURADO}&entidad_id={lead_id_a}"
        )
        assert r_list.status_code == 200
        items = r_list.data.get("results", r_list.data)
        assert [row["id_evento"] for row in items] == [str(ev_dlq_a.pk)]

        # Aislamiento cross-tenant: Empresa B no ve ni reintenta eventos de A
        assert client_b.get(f"{BASE_HUB}/outbox/{ev_dlq_a.pk}/").status_code == 404
        assert client_b.post(f"{BASE_HUB}/outbox/{ev_dlq_a.pk}/reintentar/").status_code == 404
        assert client_a.get(f"{BASE_HUB}/outbox/{ev_b.pk}/").status_code == 404

        # Solo lectura (sin POST/DELETE arbitrario sobre la cola)
        assert client_a.post(f"{BASE_HUB}/outbox/", {}, format="json").status_code == 405
        assert client_a.delete(f"{BASE_HUB}/outbox/{ev_dlq_a.pk}/").status_code == 405

        # Validaciones de query params (estado inválido, UUID inválido, NUL en key y valor, lookup malformado)
        assert client_a.get(f"{BASE_HUB}/outbox/?estado=INEXISTENTE").status_code == 400
        assert client_a.get(f"{BASE_HUB}/outbox/?entidad_id=no-uuid").status_code == 400
        assert client_a.get(f"{BASE_HUB}/outbox/?estado=DLQ%00").status_code == 400
        assert client_a.get(f"{BASE_HUB}/outbox/?mal%00key=1").status_code == 400
        assert client_a.get(f"{BASE_HUB}/outbox/------------------------------------/").status_code == 400

        # Reintentar evento ENVIADO -> 400 vía domain_error_response
        r_bad_retry = client_a.post(f"{BASE_HUB}/outbox/{ev_env_a.pk}/reintentar/")
        assert r_bad_retry.status_code == 400
        assert "FALLIDO o DLQ" in r_bad_retry.data["error"]

        # Reintentar evento DLQ -> 200 reseteado a PENDIENTE con intentos=0
        r_ok_retry = client_a.post(f"{BASE_HUB}/outbox/{ev_dlq_a.pk}/reintentar/")
        assert r_ok_retry.status_code == 200
        assert r_ok_retry.data["estado"] == EventoOutbox.Estado.PENDIENTE
        assert r_ok_retry.data["intentos"] == 0
        assert r_ok_retry.data["ultimo_error"] == ""
        assert r_ok_retry.data["procesado_en"] is None

        # PATCH sobre Lead en /api/crm/leads/{pk}/ encola EVENTO_CRM_LEAD_ACTUALIZADO sin PII
        lead_patch = crear_lead_crm(
            empresa=empresa_a,
            nombre="Luis",
            apellido="Méndez",
            email="luis.mendez@ejemplo.test",
            telefono="0414-7778899",
            propietario=user_a,
        )
        r_patch_lead = client_a.patch(
            f"/api/crm/leads/{lead_patch.pk}/",
            {"empresa_nombre": "Importadora Méndez", "mensaje": "Llamar mañana"},
            format="json",
        )
        assert r_patch_lead.status_code == 200
        ev_act = EventoOutbox.objects.get(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_ACTUALIZADO,
            entidad_id=lead_patch.pk,
        )
        payload_act_dump = json.dumps(ev_act.payload, ensure_ascii=False).lower()
        assert ev_act.payload["lead_id"] == str(lead_patch.pk)
        for pii in ("luis", "méndez", "0414", "7778899", "importadora", "llamar"):
            assert pii not in payload_act_dump

        # PATCH sobre lead anonimizado no genera EVENTO_CRM_LEAD_ACTUALIZADO adicional
        anonimizar_lead(lead_patch.pk, user_a)
        total_act_antes = EventoOutbox.objects.filter(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_ACTUALIZADO,
            entidad_id=lead_patch.pk,
        ).count()
        client_a.patch(f"/api/crm/leads/{lead_patch.pk}/", {"mensaje": ""}, format="json")
        assert (
            EventoOutbox.objects.filter(
                id_empresa=empresa_a,
                tipo_evento=EVENTO_CRM_LEAD_ACTUALIZADO,
                entidad_id=lead_patch.pk,
            ).count()
            == total_act_antes
        )

        # Helper directo con UUID inválido / evento inexistente + swagger_fake_view
        with pytest.raises(OutboxError):
            reintentar_evento_outbox("uuid-malo", empresa_ids=[empresa_a.pk])
        with pytest.raises(OutboxError):
            reintentar_evento_outbox(uuid.uuid4(), empresa_ids=[empresa_a.pk])
        vs_fake = EventoOutboxViewSet()
        vs_fake.swagger_fake_view = True
        assert list(vs_fake.get_queryset()) == []

    def test_mcp_hub_listar_y_reintentar_outbox(self, empresa_a, empresa_b, user_a):
        # Registradas en FastMCP
        registered = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert {"hub_listar_outbox", "hub_reintentar_outbox"} <= registered

        tok_read = _mcp_token(empresa_a, ["integration_hub:read"], creado_por=user_a)
        tok_write = _mcp_token(empresa_a, ["integration_hub:read", "integration_hub:write"], creado_por=user_a)

        ev_a = EventoOutbox.objects.create(
            id_empresa=empresa_a,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=uuid.uuid4(),
            clave_idempotencia="mcp-a-fallido",
            estado=EventoOutbox.Estado.FALLIDO,
            intentos=2,
            ultimo_error="Fallo temporal",
        )
        ev_b = EventoOutbox.objects.create(
            id_empresa=empresa_b,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=uuid.uuid4(),
            clave_idempotencia="mcp-b-dlq",
            estado=EventoOutbox.Estado.DLQ,
            intentos=5,
        )

        # Listado happy path + filtros (incl. empresa_id vacío opcional)
        res_list = hub_mcp.hub_listar_outbox(
            tok_read,
            empresa_id=str(empresa_a.pk),
            estado="FALLIDO",
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
        )
        assert res_list["success"] is True
        assert [row["id_evento"] for row in res_list["eventos"]] == [str(ev_a.pk)]
        res_list_blank_emp = hub_mcp.hub_listar_outbox(tok_read, empresa_id="   ")
        assert res_list_blank_emp["success"] is True
        assert any(row["id_evento"] == str(ev_a.pk) for row in res_list_blank_emp["eventos"])

        # Listado con validaciones inválidas (estado, UUID, NUL, limit=None y limit=True)
        assert hub_mcp.hub_listar_outbox(tok_read, estado="INVALIDO")["success"] is False
        assert hub_mcp.hub_listar_outbox(tok_read, empresa_id="no-uuid")["success"] is False
        assert hub_mcp.hub_listar_outbox(tok_read, tipo_evento="crm\x00bad")["success"] is False
        assert hub_mcp.hub_listar_outbox(tok_read, limit=None)["success"] is False  # type: ignore[arg-type]
        assert hub_mcp.hub_listar_outbox(tok_read, limit=True)["success"] is False

        # Cross-tenant empresa_id -> PermissionError
        with pytest.raises(PermissionError):
            hub_mcp.hub_listar_outbox(tok_read, empresa_id=str(empresa_b.pk))

        # Scope insuficiente para reintentar -> PermissionError
        with pytest.raises(PermissionError):
            hub_mcp.hub_reintentar_outbox(tok_read, empresa_id=str(empresa_a.pk), evento_id=str(ev_a.pk))

        # Reintentar evento ajeno (de B con token de A) -> error controlado
        res_ajeno = hub_mcp.hub_reintentar_outbox(tok_write, empresa_id=str(empresa_a.pk), evento_id=str(ev_b.pk))
        assert res_ajeno["success"] is False
        assert "no encontrado" in res_ajeno["error"].lower()

        # Reintentar con UUID inválido / NUL
        assert hub_mcp.hub_reintentar_outbox(tok_write, evento_id="bad-uuid")["success"] is False
        assert hub_mcp.hub_reintentar_outbox(tok_write, evento_id=f"{ev_a.pk}\x00")["success"] is False

        # Reintentar happy path
        res_retry = hub_mcp.hub_reintentar_outbox(tok_write, empresa_id=str(empresa_a.pk), evento_id=str(ev_a.pk))
        assert res_retry["success"] is True
        assert res_retry["evento"]["estado"] == EventoOutbox.Estado.PENDIENTE
        assert res_retry["evento"]["intentos"] == 0

        # Error inesperado en listado y reintento -> sanitizado sin secretos ni SQL
        with patch.object(
            EventoOutbox.objects,
            "filter",
            side_effect=RuntimeError(f"SELECT * FROM secret password={DUMMY_WRITE_KEY}"),
        ):
            res_err = hub_mcp.hub_listar_outbox(tok_read, empresa_id=str(empresa_a.pk))
        assert res_err["success"] is False
        assert DUMMY_WRITE_KEY not in res_err["error"]
        assert "SELECT *" not in res_err["error"]
