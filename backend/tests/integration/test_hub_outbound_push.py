"""
Tests exhaustivos para PR-19 (Ola B7 — Push Outbound Hub hacia Odoo + CTF-011).

100% mockeados para CI (cero red real). Cubre:
- OdooConnector: _get_write_client fail-closed, _get_model_fields (Odoo 18 memo vs <18 payment_reference/ref),
  push_pago_cobranza (borrador, confirmado + action_post + reconcile, idempotencia, validaciones Decimal),
  push_gestion_cobranza (account.move vs res.partner, escape HTML XSS-safe, idempotencia),
  _sanitizar_error_externo (R-CODE-8).
- Serializers: write_api_key en SECRET_KEYS, get_configuracion_publica, simetría fail-closed en CREATE/PATCH,
  inmutabilidad id_empresa + Matriz↔Subsidiaria, push_modo_pago, gestiones_cobranza en trigger serializer.
- SyncEngine: PUSH_METHODS, guardia opt-in push_habilitado=False, outbound (pagos, gestiones_cobranza,
  contactos, productos), bidireccional, idempotencia por registro + checksum + origen_externo, aislamiento parcial
  de errores y tenant R-CODE-1.
- Views & MCP: NulSafeFilterMixin (?search=test, ?search=\\x00), Idempotency-Key en sync y push-cobranza,
  opt-in guard HTTP 400, IDOR multi-tenant, paridad MCP (legacy + FastMCP MCP_TOOLS con CapabilityToken).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from xmlrpc.client import Fault

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import CapabilityToken, Contacto, Empresa, Usuarios
from apps.cxc.models import GestionCobranza
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.finanzas.models import AsignacionPago, MetodoPago, Pago
from apps.integration_hub import mcp as hub_mcp
from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    ConnectorDataError,
    ConnectorNotSupportedError,
)
from apps.integration_hub.connectors.odoo.client import OdooAuthError, OdooCallError, OdooXMLRPCClient
from apps.integration_hub.connectors.odoo.connector import OdooConnector
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)
from apps.integration_hub.seed_data import PROVEEDORES_BASE
from apps.integration_hub.serializers import (
    ConectorInstanciaSerializer,
    JobSincronizacionTriggerSerializer,
)
from apps.integration_hub.services.sync_engine import SyncEngine, SyncResult
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

BASE = "/api/integration-hub"


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def proveedor_odoo(db):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo",
        defaults={
            "nombre": "Odoo",
            "estado": "activo",
            "capacidades": [
                "contactos",
                "productos",
                "pedidos_venta",
                "pedidos_compra",
                "facturas_venta",
                "facturas_compra",
                "pagos",
                "gestiones_cobranza",
                "inventario",
            ],
        },
    )
    return prov


def _instancia_odoo(empresa, proveedor, **cfg_overrides):
    cfg = {
        "host": "https://qa.odoo.com",
        "db": "qa_db",
        "user": "reader@qa.com",
        "api_key": "read-secret-xyz",
        "push_habilitado": True,
        "push_modo_pago": "borrador",
        "diario_pagos_default_id": 5,
    }
    cfg.update(cfg_overrides)
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        nombre=f"Odoo {uuid.uuid4().hex[:6]}",
        estado="activo",
        configuracion=cfg,
        entidades_activas=["contactos", "productos", "pagos", "gestiones_cobranza"],
    )


# ── 1. Seed & Modelo ──────────────────────────────────────────────────────────


def test_seed_y_modelo_incluyen_gestiones_cobranza():
    choices = dict(EntidadSincronizada.TIPO_CHOICES)
    assert "gestiones_cobranza" in choices
    odoo_seed = next(p for p in PROVEEDORES_BASE if p["codigo"] == "odoo")
    assert "gestiones_cobranza" in odoo_seed["capacidades"]
    assert "gestiones_cobranza" in OdooConnector.SUPPORTED_ENTITIES


def test_base_connector_push_cobranza_y_gestion_no_soportados():
    class Dummy(BaseConnector):
        PROVIDER_NAME = "Dummy"

        def test_connection(self):  # pragma: no cover
            raise NotImplementedError

        def get_version_info(self):  # pragma: no cover
            raise NotImplementedError

    d = Dummy.__new__(Dummy)
    with pytest.raises(ConnectorNotSupportedError):
        d.push_pago_cobranza({})
    with pytest.raises(ConnectorNotSupportedError):
        d.push_gestion_cobranza({})


# ── 2. OdooConnector: write client, fields, push_pago_cobranza, push_gestion_cobranza, R-CODE-8 ──


class TestOdooConnectorOutbound:
    def test_get_write_client_fail_closed_sin_push_habilitado(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo, push_habilitado=False)
        conn = OdooConnector(inst)
        with pytest.raises(ConnectorConnectionError, match="push_habilitado=False"):
            conn._get_write_client()

    def test_get_write_client_fail_closed_asimetrico(self, empresa_a, proveedor_odoo):
        inst1 = _instancia_odoo(empresa_a, proveedor_odoo, write_user="w@qa.com")
        with pytest.raises(ConnectorConnectionError, match="write_api_key"):
            OdooConnector(inst1)._get_write_client()

        inst2 = _instancia_odoo(empresa_a, proveedor_odoo, write_api_key="wk")
        with pytest.raises(ConnectorConnectionError, match="write_user"):
            OdooConnector(inst2)._get_write_client()

    def test_get_write_client_usa_write_creds_si_simetrico(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(
            empresa_a,
            proveedor_odoo,
            write_user="writer@qa.com",
            write_api_key="write-secret-999",
        )
        conn = OdooConnector(inst)
        fake_write = MagicMock()
        fake_write.ping.return_value = True

        with patch("apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient", return_value=fake_write) as cls:
            cli1 = conn._get_write_client()
            cli2 = conn._get_write_client()

        assert cli1 is fake_write and cli2 is fake_write
        cls.assert_called_once_with("https://qa.odoo.com", "qa_db", "writer@qa.com", "write-secret-999", 30)

    def test_get_write_client_fallback_credenciales_principales_si_ninguno(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo)
        conn = OdooConnector(inst)
        fake_main = MagicMock()
        with patch.object(conn, "_get_client", return_value=fake_main) as gc:
            cli = conn._get_write_client()
        assert cli is fake_main
        gc.assert_called_once()

    def test_get_model_fields_cacheado_y_deteccion_versiones_pago(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo)
        conn = OdooConnector(inst)

        # Odoo 18: memo (sin ref)
        cli18 = MagicMock()
        cli18._get_model_fields.return_value = "not-a-set"
        cli18.call.return_value = {"id": {}, "memo": {}, "partner_id": {}}
        assert conn._get_model_fields(cli18, "account.payment") == {"id", "memo", "partner_id"}
        assert conn._get_model_fields(cli18, "account.payment") == {"id", "memo", "partner_id"}
        assert cli18.call.call_count == 1  # cacheado
        assert conn._detectar_campo_ref_pago(cli18) == "memo"

        # Odoo <18: payment_reference
        cli16 = MagicMock()
        cli16._get_model_fields.return_value = {"id", "payment_reference", "partner_id"}
        assert conn._detectar_campo_ref_pago(cli16) == "payment_reference"

        # Odoo <15: ref
        cli14 = MagicMock()
        cli14._get_model_fields.return_value = {"id", "ref", "partner_id"}
        assert conn._detectar_campo_ref_pago(cli14) == "ref"

    def test_push_pago_cobranza_borrador_e_idempotencia(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo, push_modo_pago="borrador")
        conn = OdooConnector(inst)
        cli = MagicMock()
        cli._get_model_fields.return_value = {"id", "memo", "partner_id"}
        cli.get_monedas.return_value = [{"id": 2, "name": "USD"}]
        cli.call.side_effect = [
            [],  # search existente -> vacío
            701,  # create -> 701
            [701],  # 2da llamada: search existente -> [701]
        ]
        conn._get_write_client = lambda: cli  # type: ignore[method-assign]

        payload = {
            "idempotency_key": "pago-123",
            "partner_id": 44,
            "monto": Decimal("150.25"),
            "moneda": "USD",
            "fecha": "2026-11-20",
            "referencia": "Zelle 9981",
        }
        res1 = conn.push_pago_cobranza(payload)
        res2 = conn.push_pago_cobranza(payload)

        assert res1 == "701"
        assert res2 == "701"
        assert cli.call.call_count == 3  # no volvió a llamar create ni action_post
        create_call = cli.call.call_args_list[1]
        assert create_call.args[:2] == ("account.payment", "create")
        vals = create_call.args[2][0]
        assert vals["partner_id"] == 44
        assert vals["amount"] == 150.25
        assert vals["journal_id"] == 5
        assert vals["currency_id"] == 2
        assert "[OMNI:pago-123]" in vals["memo"]

    def test_push_pago_cobranza_confirmado_ejecuta_action_post_y_reconcile(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo, push_modo_pago="confirmado")
        conn = OdooConnector(inst)
        cli = MagicMock()
        cli._get_model_fields.side_effect = lambda m: (
            {"id", "payment_reference", "move_id"} if m == "account.payment" else {"id", "account_type", "reconciled"}
        )
        cli.call.side_effect = [
            [],  # search pago existente
            805,  # create account.payment
            True,  # action_post
            [{"id": 805, "move_id": [990, "PAY/001"]}],  # read move_id
            [1001],  # search pay line
            [2001, 2002],  # search invoice lines
            True,  # reconcile
        ]
        conn._get_write_client = lambda: cli  # type: ignore[method-assign]

        res = conn.push_pago_cobranza(
            {
                "idempotency_key": "pago-conf-1",
                "partner_id": 10,
                "monto": "80.00",
                "journal_id": 9,
                "facturas_odoo_ids": [301, 302],
                "push_modo_pago": "confirmado",
            }
        )
        assert res == "805"
        calls = [c.args for c in cli.call.call_args_list]
        assert calls[1][0:2] == ("account.payment", "create")
        assert calls[1][2][0]["payment_reference"].startswith("[OMNI:pago-conf-1]")
        assert calls[2] == ("account.payment", "action_post", [[805]])
        assert ["parent_state", "=", "posted"] in calls[5][2][0]
        assert calls[6] == ("account.move.line", "reconcile", [[1001, 2001, 2002]])

    @pytest.mark.parametrize(
        "bad",
        [
            {"monto": "10", "journal_id": 1},
            {"partner_id": -1, "monto": "10", "journal_id": 1},
            {"partner_id": 1, "monto": "0", "journal_id": 1},
            {"partner_id": 1, "monto": "-5", "journal_id": 1},
            {"partner_id": 1, "monto": "abc", "journal_id": 1},
            {"partner_id": 1, "monto": "10", "journal_id": 1, "push_modo_pago": "invalido"},
        ],
    )
    def test_push_pago_cobranza_valida_entradas(self, empresa_a, proveedor_odoo, bad):
        inst = _instancia_odoo(empresa_a, proveedor_odoo)
        conn = OdooConnector(inst)
        with pytest.raises(ConnectorDataError):
            conn.push_pago_cobranza(bad)

    def test_push_gestion_cobranza_escape_html_e_idempotencia(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo)
        conn = OdooConnector(inst)
        cli = MagicMock()
        cli.call.side_effect = [
            [],  # search mail.message -> vacío
            910,  # account.move.message_post -> 910
            [910],  # 2da llamada: search mail.message -> [910]
        ]
        conn._get_write_client = lambda: cli  # type: ignore[method-assign]

        payload = {
            "idempotency_key": "gest-1",
            "factura_odoo_id": 555,
            "partner_id": 44,
            "cliente_nombre": 'Acme <script>alert("xss")</script> & Co',
            "orden_ref": "INV/<01>",
            "canal": "whatsapp<img src=x onerror=1>",
            "resultado": "promesa_pago&ok",
            "notas": "<b>Prometió</b> pagar el viernes",
            "fecha_gestion": "2026-11-20",
        }
        mid1 = conn.push_gestion_cobranza(payload)
        mid2 = conn.push_gestion_cobranza(payload)

        assert mid1 == "910"
        assert mid2 == "910"
        assert cli.call.call_count == 3
        post_call = cli.call.call_args_list[1]
        assert post_call.args[:3] == ("account.move", "message_post", [[555]])
        body = post_call.args[3]["body"]
        assert "<script>" not in body
        assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in body
        assert "&lt;img src=x onerror=1&gt;" in body
        assert "[OMNI-GESTION:gest-1]" in body

    def test_push_gestion_cobranza_fallback_res_partner(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo)
        conn = OdooConnector(inst)
        cli = MagicMock()
        cli.call.side_effect = [[], 912]
        conn._get_write_client = lambda: cli  # type: ignore[method-assign]

        mid = conn.push_gestion_cobranza(
            {
                "idempotency_key": "gest-partner-1",
                "partner_id": 77,
                "canal": "llamada",
                "resultado": "contactado",
            }
        )
        assert mid == "912"
        assert cli.call.call_args_list[1].args[:3] == ("res.partner", "message_post", [[77]])

    def test_sanitizar_error_externo_oculta_secretos_y_urls(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(
            empresa_a,
            proveedor_odoo,
            api_key="super-read-secret",
            write_api_key="super-write-secret",
        )
        conn = OdooConnector(inst)
        cli = MagicMock()
        cli._get_model_fields.return_value = {"memo"}
        cli.call.side_effect = OdooCallError(
            "Fallo https://user:secretpass@qa.odoo.com/xmlrpc con write_api_key=super-write-secret "
            "y api_key=super-read-secret\nTraceback (most recent call last):\n  File x.py"
        )
        conn._get_write_client = lambda: cli  # type: ignore[method-assign]

        with pytest.raises(ConnectorDataError) as exc_info:
            conn.push_pago_cobranza({"partner_id": 1, "monto": "10", "journal_id": 1})

        msg = str(exc_info.value)
        assert "super-read-secret" not in msg
        assert "super-write-secret" not in msg
        assert "secretpass" not in msg
        assert "Traceback" not in msg

    def test_xmlrpc_client_call_sanitiza_api_key_en_fault_y_excepcion(self):
        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_common = MagicMock()
            mock_common.authenticate.return_value = 1
            mock_common.version.return_value = {"server_version": "18.0"}
            mock_models = MagicMock()
            mock_proxy.side_effect = [mock_common, mock_models]
            client = OdooXMLRPCClient("https://qa.odoo.com", "qa", "u@qa.com", "ci-only-dummy-key-xmlrpc-123")

        mock_models.execute_kw.side_effect = Fault(
            1, "Error con ci-only-dummy-key-xmlrpc-123 en https://u:pass@qa.odoo.com"
        )
        with pytest.raises(OdooCallError) as exc_fault:
            client.call("account.payment", "search", [[]])
        assert "ci-only-dummy-key-xmlrpc-123" not in str(exc_fault.value)
        assert "u:pass@" not in str(exc_fault.value)

        mock_models.execute_kw.side_effect = RuntimeError("api_key=ci-only-dummy-key-xmlrpc-123 failed")
        with pytest.raises(OdooCallError) as exc_err:
            client.call("account.payment", "search", [[]])
        assert "ci-only-dummy-key-xmlrpc-123" not in str(exc_err.value)


# ── 3. Serializers & Matriz↔Subsidiaria ───────────────────────────────────────


class TestSerializersOutbound:
    def test_secretos_nunca_expuestos_en_configuracion_publica(self, empresa_a, proveedor_odoo):
        inst = _instancia_odoo(
            empresa_a,
            proveedor_odoo,
            write_user="writer@qa.com",
            write_api_key="write-secret-123",
            password="legacy-password",
            push_habilitado=True,
            push_modo_pago="confirmado",
            diario_pagos_default_id=8,
        )
        data = ConectorInstanciaSerializer(inst).data
        pub = data["configuracion_publica"]
        assert pub["push_habilitado"] is True
        assert pub["push_modo_pago"] == "confirmado"
        assert pub["write_user"] == "writer@qa.com"
        assert pub["tiene_write_api_key"] is True
        assert pub["diario_pagos_default_id"] == 8
        assert "api_key" not in pub
        assert "write_api_key" not in pub
        assert "password" not in pub
        assert "service_account" not in pub
        assert "write-secret-123" not in str(data)
        assert "read-secret-xyz" not in str(data)

    def test_patch_preserva_write_api_key_vacia_o_ausente_y_valida_simetria(self, empresa_a, user_a, proveedor_odoo):
        inst = _instancia_odoo(
            empresa_a,
            proveedor_odoo,
            write_user="writer@qa.com",
            write_api_key="write-secret-123",
        )
        # PATCH sin write_api_key -> conserva secreto
        resp = _client(user_a).patch(
            f"{BASE}/instancias/{inst.pk}/",
            {
                "configuracion": {
                    "host": "https://qa.odoo.com",
                    "user": "reader@qa.com",
                    "push_habilitado": True,
                    "write_api_key": "",
                }
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data
        inst.refresh_from_db()
        assert inst.get_config()["write_api_key"] == "write-secret-123"
        assert inst.get_config()["push_habilitado"] is True

        # PATCH quitando write_user mientras write_api_key sigue guardado -> 400 fail-closed
        resp_asym = _client(user_a).patch(
            f"{BASE}/instancias/{inst.pk}/",
            {"configuracion": {"host": "https://qa.odoo.com", "user": "reader@qa.com", "write_user": ""}},
            format="json",
        )
        assert resp_asym.status_code == 400

        # PATCH con push_modo_pago inválido -> 400
        resp_modo = _client(user_a).patch(
            f"{BASE}/instancias/{inst.pk}/",
            {"configuracion": {"push_modo_pago": "auto_magico"}},
            format="json",
        )
        assert resp_modo.status_code == 400

    def test_create_asimetrico_rechazado_fail_closed(self, empresa_a, user_a, proveedor_odoo):
        resp = _client(user_a).post(
            f"{BASE}/instancias/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Asimetrico",
                "configuracion": {
                    "host": "https://qa.odoo.com",
                    "user": "r@qa.com",
                    "api_key": "rk",
                    "write_user": "w@qa.com",
                },
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_inmutabilidad_id_empresa_en_patch_y_matriz_subsidiaria(
        self, empresa_a, empresa_b, user_a, moneda_usd, proveedor_odoo
    ):
        sub = Empresa.objects.create(
            nombre_legal="Subsidiaria QA", empresa_matriz=empresa_a, id_moneda_base=moneda_usd
        )
        user_sub = Usuarios.objects.create_user(username="sub_user", email="sub@test.com", password="x")
        user_sub.empresas.add(sub)

        # Matriz puede crear conector para Subsidiaria
        resp_sub = _client(user_a).post(
            f"{BASE}/instancias/",
            {
                "id_empresa": str(sub.pk),
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Odoo Subsidiaria",
                "configuracion": {"host": "https://sub.odoo.com", "user": "u", "api_key": "k"},
            },
            format="json",
        )
        assert resp_sub.status_code == 201, resp_sub.data
        inst_sub = ConectorInstancia.objects.get(nombre="Odoo Subsidiaria")
        assert inst_sub.id_empresa_id == sub.pk

        # Subsidiaria NO puede crear conector para su Matriz
        resp_up = _client(user_sub).post(
            f"{BASE}/instancias/",
            {
                "id_empresa": str(empresa_a.pk),
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Intento Matriz",
                "configuracion": {"host": "https://m.odoo.com", "user": "u", "api_key": "k"},
            },
            format="json",
        )
        assert resp_up.status_code == 400

        # Usuario de A no puede crear para B (otro tenant)
        resp_cross = _client(user_a).post(
            f"{BASE}/instancias/",
            {
                "id_empresa": str(empresa_b.pk),
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Cross",
                "configuracion": {"host": "https://b.odoo.com", "user": "u", "api_key": "k"},
            },
            format="json",
        )
        assert resp_cross.status_code == 400

        # PATCH intentando cambiar id_empresa de Matriz a Subsidiaria -> 400 inmutable
        inst_matriz = _instancia_odoo(empresa_a, proveedor_odoo)
        resp_patch = _client(user_a).patch(
            f"{BASE}/instancias/{inst_matriz.pk}/",
            {"id_empresa": str(sub.pk), "nombre": "Cambio empresa"},
            format="json",
        )
        assert resp_patch.status_code == 400
        inst_matriz.refresh_from_db()
        assert inst_matriz.id_empresa_id == empresa_a.pk

    def test_trigger_serializer_acepta_gestiones_cobranza(self):
        ser = JobSincronizacionTriggerSerializer(data={"tipo_entidad": "gestiones_cobranza", "direccion": "outbound"})
        assert ser.is_valid(), ser.errors

    def test_post_put_patch_respuestas_sin_secretos_y_rechazo_espacios(self, empresa_a, user_a, proveedor_odoo):
        resp_post = _client(user_a).post(
            f"{BASE}/instancias/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Odoo Secreto Resp",
                "configuracion": {
                    "host": "https://qa.odoo.com",
                    "user": "reader@qa.com",
                    "api_key": "ci-only-dummy-key-read-no-leak",
                    "write_user": "writer@qa.com",
                    "write_api_key": "ci-only-dummy-key-write-no-leak",
                    "password": "ci-only-dummy-key-legacy-pass",
                },
            },
            format="json",
        )
        assert resp_post.status_code == 201, resp_post.data
        inst_pk = resp_post.data["id_conector"]

        resp_put = _client(user_a).put(
            f"{BASE}/instancias/{inst_pk}/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Odoo Secreto PUT",
                "configuracion": {
                    "host": "https://qa2.odoo.com",
                    "user": "reader2@qa.com",
                    "api_key": "ci-only-dummy-key-put-read",
                    "write_user": "writer2@qa.com",
                    "write_api_key": "ci-only-dummy-key-put-write",
                },
            },
            format="json",
        )
        assert resp_put.status_code == 200, resp_put.data

        resp_patch = _client(user_a).patch(
            f"{BASE}/instancias/{inst_pk}/",
            {"configuracion": {"host": "https://qa3.odoo.com", "api_key": "ci-only-dummy-key-patch-read"}},
            format="json",
        )
        assert resp_patch.status_code == 200, resp_patch.data

        for resp, secrets_sent in (
            (
                resp_post,
                (
                    "ci-only-dummy-key-read-no-leak",
                    "ci-only-dummy-key-write-no-leak",
                    "ci-only-dummy-key-legacy-pass",
                ),
            ),
            (resp_put, ("ci-only-dummy-key-put-read", "ci-only-dummy-key-put-write")),
            (resp_patch, ("ci-only-dummy-key-patch-read", "ci-only-dummy-key-put-write")),
        ):
            assert "configuracion" not in resp.data
            pub = resp.data["configuracion_publica"]
            for secret_key in ("api_key", "write_api_key", "password", "service_account"):
                assert secret_key not in pub
            raw_json = json.dumps(resp.data, default=str)
            for s_val in secrets_sent:
                assert s_val not in raw_json
                assert s_val not in resp.content.decode("utf-8")

        # Espacios en blanco rechazados en host/user/api_key
        bad_post = _client(user_a).post(
            f"{BASE}/instancias/",
            {
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Espacios",
                "configuracion": {"host": "   ", "user": "u", "api_key": "k"},
            },
            format="json",
        )
        assert bad_post.status_code == 400


# ── 4. SyncEngine Outbound & Bidireccional ────────────────────────────────────


class _FakePushConnector(BaseConnector):
    PROVIDER_CODE = "fake_push"
    PROVIDER_NAME = "FakePush"
    SUPPORTED_ENTITIES = ["pagos", "gestiones_cobranza", "contactos", "productos"]

    pull_data: list[dict] = []
    pull_productos_data: list[dict] = []
    pagos_llamados: list[dict] = []
    gestiones_llamadas: list[dict] = []
    contactos_llamados: list[dict] = []
    productos_llamados: list[dict] = []
    fail_on_id: str | None = None
    seq = 100

    def test_connection(self):  # pragma: no cover
        raise NotImplementedError

    def get_version_info(self):  # pragma: no cover
        return {}

    def pull_contactos(self, desde=None, limite=500):
        return list(self.pull_data)

    def pull_productos(self, desde=None, limite=500):
        return list(self.pull_productos_data)

    def pull_pagos(self, desde=None, limite=500):
        return []

    def push_pago_cobranza(self, datos: dict) -> str:
        if self.fail_on_id and datos.get("id_omni") == self.fail_on_id:
            raise ConnectorDataError("Pago sin diario válido con api_key=secreto-oculto")
        self.pagos_llamados.append(datos)
        _FakePushConnector.seq += 1
        return str(_FakePushConnector.seq)

    def push_gestion_cobranza(self, datos: dict) -> str:
        self.gestiones_llamadas.append(datos)
        _FakePushConnector.seq += 1
        return str(_FakePushConnector.seq)

    def push_contacto(self, datos: dict) -> str:
        self.contactos_llamados.append(datos)
        _FakePushConnector.seq += 1
        return datos.get("id_externo") or str(_FakePushConnector.seq)

    def push_producto(self, datos: dict) -> str:
        self.productos_llamados.append(datos)
        _FakePushConnector.seq += 1
        return datos.get("id_externo") or str(_FakePushConnector.seq)


@pytest.fixture
def fake_push_env(empresa_a):
    registry.register(_FakePushConnector)
    _FakePushConnector.pull_data = []
    _FakePushConnector.pull_productos_data = []
    _FakePushConnector.pagos_llamados = []
    _FakePushConnector.gestiones_llamadas = []
    _FakePushConnector.contactos_llamados = []
    _FakePushConnector.productos_llamados = []
    _FakePushConnector.fail_on_id = None
    _FakePushConnector.seq = 100

    prov = ConectorProveedor.objects.create(
        codigo="fake_push",
        nombre="Fake Push",
        capacidades=["contactos", "productos", "pagos", "gestiones_cobranza"],
    )
    inst = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov,
        nombre="Conector Fake Push",
        estado="activo",
        configuracion={"host": "h", "user": "u", "api_key": "secreto-oculto", "push_habilitado": True},
        entidades_activas=["contactos", "productos", "pagos", "gestiones_cobranza"],
    )
    yield inst
    registry._registry.pop("fake_push", None)


class TestSyncEngineOutbound:
    def test_sync_engine_outbound_pagos_idempotente_y_fallo_parcial_multi_tenant(
        self, fake_push_env, empresa_a, empresa_b, moneda_usd
    ):
        metodo_a = MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="Zelle", tipo_metodo="OTRO")
        metodo_b = MetodoPago.objects.create(empresa=empresa_b, nombre_metodo="Zelle", tipo_metodo="OTRO")
        contacto_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Cliente A", es_cliente=True)
        contacto_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Cliente B", es_cliente=True)

        EntidadSincronizada.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            id_externo="44",
            id_omni=str(contacto_a.pk),
        )
        cxc_a = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente_externo_id="44",
            cliente_externo_nombre="Cliente A",
            monto=Decimal("200.00"),
            fecha_emision=date(2026, 11, 1),
            fecha_vencimiento=date(2026, 11, 15),
            referencia_externa="odoo:out_invoice:901",
        )

        # Pago válido de empresa A
        pago_ok = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_a,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("100.5000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_a,
            referencia="REF-OK",
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_a,
            id_pago=pago_ok,
            tipo_documento="CUENTA_POR_COBRAR",
            id_documento=cxc_a.pk,
            id_cxc=cxc_a,
            monto_asignado_pago=Decimal("100.5000"),
            monto_asignado_documento=Decimal("100.50"),
            id_moneda_documento=moneda_usd,
        )
        # Pago de A que fallará en conector (aislado)
        pago_err = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_a,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("25.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_a,
            referencia="REF-ERR",
        )
        # Pago ya importado desde Odoo (no debe re-empujarse)
        Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_a,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_a,
            referencia="odoo:555 REF",
        )
        # Pago de empresa B (nunca debe tocarse — R-CODE-1)
        Pago.objects.create(
            id_empresa=empresa_b,
            id_contacto=contacto_b,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("999.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_b,
            referencia="TENANT-B",
        )

        _FakePushConnector.fail_on_id = str(pago_err.pk)
        job1 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
        )
        res1 = SyncEngine().ejecutar_job(job1)
        assert res1.creados == 1
        assert res1.omitidos == 1
        assert res1.fallidos == 1
        job1.refresh_from_db()
        assert job1.estado == "completado_con_errores"
        # Monto Decimal (R-CODE-4) + factura resuelta + secreto sanitizado en log
        assert len(_FakePushConnector.pagos_llamados) == 1
        assert isinstance(_FakePushConnector.pagos_llamados[0]["monto"], Decimal)
        assert _FakePushConnector.pagos_llamados[0]["facturas_odoo_ids"] == [901]
        log_err = LogDetalleSincronizacion.objects.get(id_job=job1, operacion="error")
        assert "secreto-oculto" not in log_err.mensaje_error

        # Re-ejecución idempotente: pago_ok ahora se omite (no se duplica)
        _FakePushConnector.fail_on_id = None
        job2 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
            parametros={"sync_completo": True},
        )
        res2 = SyncEngine().ejecutar_job(job2)
        assert res2.creados == 1  # solo pago_err que antes falló
        assert res2.omitidos == 2  # pago_ok + odoo:555
        assert len(_FakePushConnector.pagos_llamados) == 2

    def test_sync_engine_outbound_gestiones_contactos_productos_y_bidireccional(
        self, fake_push_env, empresa_a, empresa_b, moneda_usd
    ):
        cxc_a = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente_externo_id="88",
            cliente_externo_nombre="Deudor A",
            monto=Decimal("50.00"),
            fecha_emision=date(2026, 11, 1),
            fecha_vencimiento=date(2026, 11, 10),
            referencia_externa="odoo:out_invoice:333",
        )
        GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id="88",
            cliente_nombre="Deudor A",
            cxc=cxc_a,
            canal="whatsapp",
            resultado="promesa_pago",
            notas="Paga mañana",
            fecha_gestion=date(2026, 11, 20),
        )
        GestionCobranza.objects.create(
            empresa=empresa_b,
            cliente_id="99",
            cliente_nombre="Deudor B",
            canal="email",
            resultado="contactado",
            fecha_gestion=date(2026, 11, 20),
        )

        job_g = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="gestiones_cobranza",
            direccion="outbound",
            estado="pendiente",
        )
        res_g = SyncEngine().ejecutar_job(job_g)
        assert res_g.creados == 1
        assert len(_FakePushConnector.gestiones_llamadas) == 1
        assert _FakePushConnector.gestiones_llamadas[0]["factura_odoo_id"] == 333
        assert _FakePushConnector.gestiones_llamadas[0]["partner_id"] == 88

        # Productos outbound
        unidad = UnidadMedida.objects.create(id_empresa=empresa_a, nombre="Und", abreviatura="U", tipo="CANTIDAD")
        cat = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="General")
        Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Filtro Aceite",
            sku="FA-01",
            id_unidad_medida_base=unidad,
            id_categoria=cat,
            id_moneda_precio=moneda_usd,
            precio_venta_sugerido=Decimal("15.00"),
        )
        job_p = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="productos",
            direccion="outbound",
            estado="pendiente",
        )
        res_p = SyncEngine().ejecutar_job(job_p)
        assert res_p.creados == 1
        assert len(_FakePushConnector.productos_llamados) == 1

        # Bidireccional contactos: pull crea 1 contacto, push crea el contacto local nuevo y actualiza el importado
        Contacto.objects.create(id_empresa=empresa_a, nombre="Local Bidi", email="local@a.com", es_cliente=True)
        _FakePushConnector.pull_data = [
            {"id_externo": "ext-1", "nombre": "Importado Bidi", "email": "bidi@a.com", "_checksum": "c1"}
        ]
        job_bidi = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            direccion="bidireccional",
            estado="pendiente",
        )
        res_bidi = SyncEngine().ejecutar_job(job_bidi)
        assert res_bidi.creados >= 2  # pull (1) + push local (1)
        assert res_bidi.actualizados >= 1
        assert len(_FakePushConnector.contactos_llamados) >= 2


# ── 5. Views, Idempotency-Key, NulSafeFilterMixin, IDOR & MCP Parity ─────────


class TestViewsYMcpOutbound:
    def test_trigger_sync_y_push_cobranza_opt_in_guard_400(self, empresa_a, user_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo, push_habilitado=False)

        r1 = _client(user_a).post(
            f"{BASE}/instancias/{inst.pk}/sync/",
            {"tipo_entidad": "pagos", "direccion": "outbound"},
            format="json",
        )
        assert r1.status_code == 400
        assert "push_habilitado=False" in r1.data["error"]

        r2 = _client(user_a).post(
            f"{BASE}/instancias/{inst.pk}/sync/",
            {"tipo_entidad": "pagos", "direccion": "bidireccional"},
            format="json",
        )
        assert r2.status_code == 400

        r3 = _client(user_a).post(
            f"{BASE}/instancias/{inst.pk}/push-cobranza/",
            {"tipo": "todos"},
            format="json",
        )
        assert r3.status_code == 400
        assert "push_habilitado=False" in r3.data["error"]

    def test_idempotency_key_en_trigger_sync_y_push_cobranza(self, empresa_a, user_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo, push_habilitado=True)

        with patch("apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="task-1")
            r1 = _client(user_a).post(
                f"{BASE}/instancias/{inst.pk}/sync/",
                {"tipo_entidad": "gestiones_cobranza", "direccion": "outbound"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="sync-idem-1",
            )
            r2 = _client(user_a).post(
                f"{BASE}/instancias/{inst.pk}/sync/",
                {"tipo_entidad": "gestiones_cobranza", "direccion": "outbound"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="sync-idem-1",
            )
            # Misma key con otros parámetros -> 422
            r_mismatch = _client(user_a).post(
                f"{BASE}/instancias/{inst.pk}/sync/",
                {"tipo_entidad": "pagos", "direccion": "outbound"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="sync-idem-1",
            )

            assert r1.status_code == 202
            assert r2.status_code == 202
            assert r1.data["id_job"] == r2.data["id_job"]
            assert r_mismatch.status_code == 422
            assert mock_delay.call_count == 1

            # push-cobranza con Idempotency-Key
            p1 = _client(user_a).post(
                f"{BASE}/instancias/{inst.pk}/push-cobranza/",
                {"tipo": "pagos", "push_modo_pago": "confirmado"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="pc-idem-1",
            )
            p2 = _client(user_a).post(
                f"{BASE}/instancias/{inst.pk}/push-cobranza/",
                {"tipo": "pagos", "push_modo_pago": "confirmado"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="pc-idem-1",
            )
            p_mismatch = _client(user_a).post(
                f"{BASE}/instancias/{inst.pk}/push-cobranza/",
                {"tipo": "gestiones_cobranza"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="pc-idem-1",
            )

            assert p1.status_code == 202
            assert p2.status_code == 202
            assert p1.data["job_id"] == p2.data["job_id"]
            assert p_mismatch.status_code == 422
            assert mock_delay.call_count == 2

    def test_idor_aislamiento_tenant_y_nul_safe_search(self, empresa_a, empresa_b, user_a, user_b, proveedor_odoo):
        inst_a = _instancia_odoo(empresa_a, proveedor_odoo, push_habilitado=True)
        JobSincronizacion.objects.create(
            id_instancia=inst_a,
            tipo_entidad="gestiones_cobranza",
            direccion="outbound",
            estado="completado",
        )

        # Tenant B recibe 404 en push-cobranza / sync / detalle sobre instancia de A
        assert (
            _client(user_b)
            .post(f"{BASE}/instancias/{inst_a.pk}/push-cobranza/", {"tipo": "todos"}, format="json")
            .status_code
            == 404
        )
        assert (
            _client(user_b)
            .post(
                f"{BASE}/instancias/{inst_a.pk}/sync/",
                {"tipo_entidad": "pagos", "direccion": "outbound"},
                format="json",
            )
            .status_code
            == 404
        )

        # ?search=test no da FieldError 500 (Schemathesis fix), y ?search=\x00 da 400
        assert _client(user_a).get(f"{BASE}/instancias/?search=Odoo").status_code == 200
        assert _client(user_a).get(f"{BASE}/jobs/?search=gestiones").status_code == 200
        assert _client(user_a).get(f"{BASE}/instancias/?search=%00").status_code == 400
        assert _client(user_a).get(f"{BASE}/jobs/?search=%00").status_code == 400

    def test_mcp_parity_y_capability_token_rls(self, empresa_a, empresa_b, proveedor_odoo):
        inst_a = _instancia_odoo(empresa_a, proveedor_odoo, push_habilitado=False)
        tok_read = CapabilityToken.objects.create(empresa=empresa_a, nombre="hub-r", scopes=["integration_hub:read"])
        tok_write = CapabilityToken.objects.create(empresa=empresa_a, nombre="hub-w", scopes=["integration_hub:write"])

        res_list = hub_mcp.integration_hub_listar_conectores(str(tok_read.token), str(empresa_a.id_empresa))
        assert len(res_list["conectores"]) == 1
        assert res_list["conectores"][0]["push_habilitado"] is False

        # push_habilitado=False -> bloquea outbound por MCP
        res_blocked = hub_mcp.integration_hub_push_cobranza(
            str(tok_write.token), str(empresa_a.id_empresa), str(inst_a.pk)
        )
        assert res_blocked["success"] is False
        assert "push_habilitado=False" in res_blocked["message"]

        # Activar push_habilitado y probar sync bidireccional + push_cobranza por MCP
        inst_a.configuracion = {**inst_a.get_config(), "push_habilitado": True}
        inst_a.save(update_fields=["configuracion"])

        with patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay", return_value=MagicMock(id="mcp-t1")
        ):
            res_sync = hub_mcp.integration_hub_sincronizar(
                str(tok_write.token),
                str(empresa_a.id_empresa),
                str(inst_a.pk),
                "gestiones_cobranza",
                direccion="outbound",
            )
            res_pc = hub_mcp.integration_hub_push_cobranza(
                str(tok_write.token),
                str(empresa_a.id_empresa),
                str(inst_a.pk),
                tipo="todos",
            )

        assert res_sync["success"] is True
        assert res_pc["success"] is True
        assert len(res_pc["job_ids"]) == 2

        # Cross-tenant vía MCP rechazado
        with pytest.raises(PermissionError):
            hub_mcp.integration_hub_push_cobranza(str(tok_write.token), str(empresa_b.id_empresa), str(inst_a.pk))

        # Scope insuficiente rechazado
        with pytest.raises(PermissionError):
            hub_mcp.integration_hub_push_cobranza(str(tok_read.token), str(empresa_a.id_empresa), str(inst_a.pk))

        # Tools MCP test_conector y estado_sync + errores de validación
        with patch.object(OdooConnector, "test_connection") as mock_tc:
            from apps.integration_hub.connectors.base import TestConnectionResult

            mock_tc.return_value = TestConnectionResult(success=True, message="OK QA", version="18.0")
            res_tc = hub_mcp.integration_hub_test_conector(
                str(tok_read.token), str(empresa_a.id_empresa), str(inst_a.pk)
            )
        assert res_tc["success"] is True

        res_estado = hub_mcp.integration_hub_estado_sync(str(tok_read.token), str(empresa_a.id_empresa))
        assert "ultima_24h" in res_estado

        assert hub_mcp.sincronizar(str(empresa_a.id_empresa), str(inst_a.pk), "entidad_mala")["success"] is False
        assert (
            hub_mcp.sincronizar(str(empresa_a.id_empresa), str(inst_a.pk), "pagos", direccion="invalida")["success"]
            is False
        )
        assert hub_mcp.push_cobranza(str(empresa_a.id_empresa), str(inst_a.pk), tipo="mala")["success"] is False
        assert (
            hub_mcp.push_cobranza(str(empresa_a.id_empresa), str(inst_a.pk), push_modo_pago="invalido")["success"]
            is False
        )
        assert hub_mcp.push_cobranza(str(empresa_a.id_empresa), str(uuid.uuid4()))["success"] is False

        inst_a.estado = "error"
        inst_a.save(update_fields=["estado"])
        assert hub_mcp.sincronizar(str(empresa_a.id_empresa), str(inst_a.pk), "pagos")["success"] is False
        assert hub_mcp.push_cobranza(str(empresa_a.id_empresa), str(inst_a.pk))["success"] is False

        inst_a.estado = "activo"
        inst_a.configuracion = {**inst_a.get_config(), "push_habilitado": False}
        inst_a.save(update_fields=["estado", "configuracion"])
        assert (
            hub_mcp.sincronizar(str(empresa_a.id_empresa), str(inst_a.pk), "pagos", direccion="outbound")["success"]
            is False
        )

        inst_a.configuracion = {**inst_a.get_config(), "push_habilitado": True}
        inst_a.save(update_fields=["configuracion"])
        with patch("apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay", side_effect=RuntimeError("broker")):
            res_sync_err = hub_mcp.sincronizar(
                str(empresa_a.id_empresa), str(inst_a.pk), "pagos", direccion="outbound", sync_completo=True
            )
            res_pc_err = hub_mcp.push_cobranza(
                str(empresa_a.id_empresa),
                str(inst_a.pk),
                tipo="pagos",
                ids=[str(uuid.uuid4())],
                push_modo_pago="confirmado",
            )
        assert res_sync_err["success"] is False
        assert res_pc_err["success"] is False

    def test_mcp_rechaza_uuids_invalidos_controlados(self, empresa_a, proveedor_odoo):
        inst_a = _instancia_odoo(empresa_a, proveedor_odoo, push_habilitado=True)
        for res in (
            hub_mcp.test_conector(str(empresa_a.id_empresa), "not-a-uuid"),
            hub_mcp.test_conector("not-a-uuid", str(inst_a.pk)),
            hub_mcp.sincronizar(str(empresa_a.id_empresa), "not-a-uuid", "pagos"),
            hub_mcp.push_cobranza(str(empresa_a.id_empresa), "not-a-uuid"),
            hub_mcp.push_cobranza(str(empresa_a.id_empresa), str(inst_a.pk), ids=["bad-uuid"]),
            hub_mcp.push_cobranza(str(empresa_a.id_empresa), str(inst_a.pk), ids="no-es-lista"),  # type: ignore[arg-type]
        ):
            assert res["success"] is False
            assert "message" in res


# ── 6. Cobertura adicional de edge-cases (Odoo, Serializers, SyncEngine, Views) ─


def _odoo_conn(cfg: dict) -> OdooConnector:
    inst = MagicMock()
    inst.get_config.return_value = dict(cfg)
    return OdooConnector(inst)


class TestEdgeCasesOutboundCobertura:
    def test_odoo_connector_write_client_fields_y_errores(self):
        cfg = {
            "host": "https://qa.odoo.com",
            "db": "qa_db",
            "user": "reader@qa.com",
            "api_key": "read-key",
            "write_user": "writer@qa.com",
            "write_api_key": "write-secret-xyz",
            "push_habilitado": True,
            "diario_pagos_default_id": 5,
        }
        conn = _odoo_conn(cfg)
        # Re-conexión cuando ping cached del write client falla o lanza excepción
        bad_client = MagicMock()
        bad_client.ping.return_value = False
        conn._write_client = bad_client
        with patch("apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient") as mock_cls:
            new_client = MagicMock()
            mock_cls.return_value = new_client
            assert conn._get_write_client() is new_client

        err_client = MagicMock()
        err_client.ping.side_effect = RuntimeError("timeout")
        conn._write_client = err_client
        with patch(
            "apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient",
            side_effect=OdooAuthError("bad write-secret-xyz"),
        ):
            with pytest.raises(ConnectorConnectionError) as exc_info:
                conn._get_write_client()
        assert "write-secret-xyz" not in str(exc_info.value)

        # Falta host en write client
        conn_no_host = _odoo_conn({"write_user": "w", "write_api_key": "k", "push_habilitado": True})
        with pytest.raises(ConnectorConnectionError, match="host"):
            conn_no_host._get_write_client()

        # _get_model_fields vía fields_get XML-RPC + caché + fallback vacío
        rpc_client = MagicMock(spec=["call"])
        rpc_client.call.return_value = {"id": {}, "memo": {}}
        assert "memo" in conn._get_model_fields(rpc_client, "account.payment")
        assert "memo" in conn._get_model_fields(rpc_client, "account.payment")  # desde caché
        assert rpc_client.call.call_count == 1

        rpc_bad = MagicMock(spec=["call"])
        rpc_bad.call.side_effect = RuntimeError("rpc fail")
        assert conn._get_model_fields(rpc_bad, "res.partner") == set()
        assert conn._detectar_campo_ref_pago(rpc_bad) == "memo"

    def test_odoo_conciliacion_odoo_lt18_y_validaciones_push(self):
        conn = _odoo_conn(
            {
                "host": "https://qa.odoo.com",
                "db": "qa_db",
                "user": "reader@qa.com",
                "api_key": "read-key",
                "push_habilitado": True,
                "diario_pagos_default_id": 5,
            }
        )
        # Conciliación en Odoo <18 (account_internal_type) sin move_id + líneas vacías
        client_v17 = MagicMock()
        client_v17._get_model_fields.side_effect = lambda m: (
            {"account_internal_type"} if m == "account.move.line" else {"ref"}
        )
        client_v17.call.side_effect = [
            [],  # search account.payment -> ninguno previo
            10,  # create
            True,  # action_post
            [{"id": 10, "move_id": False}],  # read payment sin move_id
            [],  # pay_line_ids vacío
            [],  # inv_line_ids vacío
        ]
        with patch.object(conn, "_get_write_client", return_value=client_v17):
            pid = conn.push_pago_cobranza(
                {
                    "partner_id": 7,
                    "monto": Decimal("10.00"),
                    "push_modo_pago": "confirmado",
                    "facturas_odoo_ids": [None, 200],
                }
            )
        assert pid == "10"

        # Validaciones de entrada push_pago_cobranza
        for bad_data in (
            {"partner_id": "abc", "monto": "10", "journal_id": 5},
            {"partner_id": 1, "journal_id": 5},
            {"partner_id": 1, "monto": "10", "journal_id": "bad"},
            {"partner_id": 1, "monto": "10", "journal_id": -3},
            {"partner_id": 1, "monto": "10", "journal_id": 5, "facturas_odoo_ids": ["not-int"]},
        ):
            with pytest.raises(ConnectorDataError):
                conn.push_pago_cobranza(bad_data)

        conn_no_journal = _odoo_conn({"push_habilitado": True})
        with pytest.raises(ConnectorDataError, match="journal_id"):
            conn_no_journal.push_pago_cobranza({"partner_id": 1, "monto": "10"})

        # OdooAuthError dentro de push_pago_cobranza -> ConnectorConnectionError sanitizado
        auth_fail_client = MagicMock()
        auth_fail_client._get_model_fields.return_value = {"memo"}
        auth_fail_client.call.side_effect = OdooAuthError("auth failed read-key")
        with patch.object(conn, "_get_write_client", return_value=auth_fail_client):
            with pytest.raises(ConnectorConnectionError) as exc_auth:
                conn.push_pago_cobranza({"partner_id": 1, "monto": "10"})
        assert "read-key" not in str(exc_auth.value)

        # Validaciones y variaciones de push_gestion_cobranza
        for bad_g in (
            {"factura_odoo_id": "bad"},
            {"partner_id": "bad"},
            {},
            {"partner_id": 0},
        ):
            with pytest.raises(ConnectorDataError):
                conn.push_gestion_cobranza(bad_g)

        msg_client = MagicMock()
        msg_client.call.side_effect = [
            [],  # search previo
            {"id": 501},  # message_post retorna dict
            [],
            [502],  # message_post retorna lista
            OdooAuthError("bad read-key"),
        ]
        with patch.object(conn, "_get_write_client", return_value=msg_client):
            assert (
                conn.push_gestion_cobranza(
                    {
                        "partner_id": 9,
                        "canal": "email",
                        "resultado": "contactado",
                        "proxima_accion": "2026-12-01",
                    }
                )
                == "501"
            )
            assert conn.push_gestion_cobranza({"partner_id": 9, "idempotency_key": "k2"}) == "502"
            with pytest.raises(ConnectorConnectionError) as exc_g_auth:
                conn.push_gestion_cobranza({"partner_id": 9, "idempotency_key": "k3"})
            assert "read-key" not in str(exc_g_auth.value)

        call_fail_client = MagicMock()
        call_fail_client.call.side_effect = OdooCallError("rpc err read-key")
        with patch.object(conn, "_get_write_client", return_value=call_fail_client):
            with pytest.raises(ConnectorDataError) as exc_g_call:
                conn.push_gestion_cobranza({"partner_id": 9, "idempotency_key": "k4"})
            assert "read-key" not in str(exc_g_call.value)

    def test_serializer_validaciones_y_views_filtros(self, empresa_a, empresa_b, user_a, proveedor_odoo):
        inst = _instancia_odoo(empresa_a, proveedor_odoo, write_user="w@qa.com", write_api_key="old-write-key")
        # PATCH manteniendo la misma id_empresa y actualizando write_api_key + diario validos
        resp_ok = _client(user_a).patch(
            f"{BASE}/instancias/{inst.pk}/",
            {
                "id_empresa": str(empresa_a.pk),
                "configuracion": {
                    "host": "https://qa.odoo.com",
                    "user": "reader@qa.com",
                    "api_key": "",
                    "write_user": "w@qa.com",
                    "write_api_key": "new-write-key",
                    "push_habilitado": True,
                    "push_modo_pago": "confirmado",
                    "diario_pagos_default_id": 9,
                },
            },
            format="json",
        )
        assert resp_ok.status_code == 200
        inst.refresh_from_db()
        assert inst.get_config()["write_api_key"] == "new-write-key"
        assert inst.get_config()["diario_pagos_default_id"] == 9

        # POST con id_empresa ajena -> 400
        resp_foreign = _client(user_a).post(
            f"{BASE}/instancias/",
            {
                "id_empresa": str(empresa_b.pk),
                "id_proveedor": str(proveedor_odoo.pk),
                "nombre": "Ajena",
                "configuracion": {"host": "https://h", "user": "u", "api_key": "k"},
            },
            format="json",
        )
        assert resp_foreign.status_code == 400

        # Validaciones de push_habilitado y diario_pagos_default_id
        for bad_cfg in (
            {"host": "h", "user": "u", "api_key": "k", "push_habilitado": "si"},
            {"host": "h", "user": "u", "api_key": "k", "diario_pagos_default_id": True},
            {"host": "h", "user": "u", "api_key": "k", "diario_pagos_default_id": "abc"},
            {"host": "h", "user": "u", "api_key": "k", "diario_pagos_default_id": 0},
        ):
            r = _client(user_a).patch(
                f"{BASE}/instancias/{inst.pk}/",
                {"configuracion": bad_cfg},
                format="json",
            )
            assert r.status_code == 400

        # push-cobranza: estado=error -> 400; fallback síncrono + ids/journal_id/sync_completo + Idempotency-Key inválida
        inst.estado = "error"
        inst.save(update_fields=["estado"])
        assert (
            _client(user_a)
            .post(f"{BASE}/instancias/{inst.pk}/push-cobranza/", {"tipo": "todos"}, format="json")
            .status_code
            == 400
        )

        inst.estado = "activo"
        inst.save(update_fields=["estado"])
        assert (
            _client(user_a)
            .post(
                f"{BASE}/instancias/{inst.pk}/push-cobranza/",
                {"tipo": "pagos"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="bad\x00key",
            )
            .status_code
            == 400
        )

        with patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay", side_effect=RuntimeError("no celery")
        ):
            with patch.object(SyncEngine, "ejecutar_job", return_value=MagicMock()) as mock_ej:
                r_fb = _client(user_a).post(
                    f"{BASE}/instancias/{inst.pk}/push-cobranza/",
                    {
                        "tipo": "pagos",
                        "ids": [str(uuid.uuid4())],
                        "journal_id": 9,
                        "sync_completo": True,
                    },
                    format="json",
                )
        assert r_fb.status_code == 202
        assert mock_ej.called

        # JobSincronizacionViewSet filtros instancia / estado / \x00
        assert _client(user_a).get(f"{BASE}/jobs/?instancia={inst.pk}&estado=pendiente").status_code == 200
        assert _client(user_a).get(f"{BASE}/jobs/?estado=pend%00").status_code == 400

        # NUL check directo en list_entidades y preview_data
        from apps.integration_hub.views import ConectorInstanciaViewSet
        from rest_framework.exceptions import ValidationError as DRFValidationError

        vs = ConectorInstanciaViewSet()
        with pytest.raises(DRFValidationError):
            vs.list_entidades(MagicMock(), pk=str(inst.pk), tipo_entidad="pagos\x00")
        with pytest.raises(DRFValidationError):
            vs.preview_data(MagicMock(), pk=str(inst.pk), tipo_entidad="pagos\x00")

    def test_sync_engine_resolvers_filtros_y_errores(self, fake_push_env, empresa_a, moneda_usd):
        from apps.crm.models import Cliente
        from apps.cuentas_por_pagar.models import CuentaPorPagar
        from apps.proveedores.models import Proveedor
        from apps.ventas.models import FacturaFiscal

        engine = SyncEngine()
        # _sanitizar_error delegando al conector
        dummy_conn = MagicMock()
        dummy_conn._sanitizar_error_externo.return_value = "clean-err"
        assert engine._sanitizar_error(dummy_conn, fake_push_env, RuntimeError("raw")) == "clean-err"
        assert engine._parse_odoo_int_id("no-numerico") is None

        metodo = MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="Transf", tipo_metodo="TRANSFERENCIA")
        cli = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cli Ref", rif="J123456789", referencia_externa="odoo:71"
        )
        contacto_cli = Contacto.objects.create(id_empresa=empresa_a, nombre="C Cli", es_cliente=True)
        cli.contacto = contacto_cli
        cli.save(update_fields=["contacto"])

        prov = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Prov Ref", rif="J987654321", referencia_externa="odoo:81"
        )
        contacto_prov = Contacto.objects.create(id_empresa=empresa_a, nombre="C Prov", es_proveedor=True)
        prov.contacto = contacto_prov
        prov.save(update_fields=["contacto"])

        ff = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cli,
            numero_control="00-01",
            numero_factura="F-01",
            fecha_emision=date(2026, 11, 1),
            monto_total=Decimal("100.00"),
            id_moneda=moneda_usd,
            referencia_externa="odoo:out_invoice:301",
        )
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            monto_total=Decimal("50.00"),
            monto_pendiente=Decimal("50.00"),
            fecha_emision=date(2026, 11, 1),
            fecha_vencimiento=date(2026, 11, 15),
            referencia_externa="odoo:in_invoice:401",
        )

        # Resolvers de pago (Cliente, Proveedor, FacturaFiscal, Asig Factura/CxP, None)
        pago_c = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cli,
            id_factura=ff,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("20.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        assert engine._resolver_partner_odoo_de_pago(pago_c, fake_push_env) == 71
        assert engine._resolver_facturas_odoo_de_pago(pago_c, fake_push_env) == [301]

        pago_p = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_prov,
            tipo_operacion="EGRESO",
            tipo_documento="CXP",
            fecha_pago=timezone.now(),
            monto=Decimal("50.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_prov,
            id_pago=pago_p,
            tipo_documento="CUENTA_POR_PAGAR",
            id_documento=cxp.pk,
            id_cxp=cxp,
            monto_asignado_pago=Decimal("50.00"),
            monto_asignado_documento=Decimal("50.00"),
            id_moneda_documento=moneda_usd,
        )
        assert engine._resolver_partner_odoo_de_pago(pago_p, fake_push_env) == 81
        assert engine._resolver_facturas_odoo_de_pago(pago_p, fake_push_env) == [401]

        pago_f_only = Pago.objects.create(
            id_empresa=empresa_a,
            id_factura=ff,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("5.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        assert engine._resolver_partner_odoo_de_pago(pago_f_only, fake_push_env) == 71

        pago_none = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("5.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        assert engine._resolver_partner_odoo_de_pago(pago_none, fake_push_env) is None

        # Resolvers de gestión (Cliente, EntidadSincronizada, None)
        g_cli = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id=str(cli.pk),
            canal="email",
            resultado="contactado",
            fecha_gestion=date(2026, 11, 20),
        )
        assert engine._resolver_partner_odoo_de_gestion(g_cli, fake_push_env) == 71

        g_none = GestionCobranza.objects.create(
            empresa=empresa_a,
            canal="llamada",
            resultado="no_contesta",
            fecha_gestion=date(2026, 11, 20),
        )
        assert engine._resolver_partner_odoo_de_gestion(g_none, fake_push_env) is None

        # Contacto con latitud/longitud y filtros ids / desde + Producto ya mapeado (id_externo)
        c_geo = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Geo",
            es_cliente=True,
            latitud=Decimal("10.500000"),
            longitud=Decimal("-66.900000"),
        )
        unidad = UnidadMedida.objects.create(id_empresa=empresa_a, nombre="Und2", abreviatura="U2", tipo="CANTIDAD")
        cat = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat2")
        prod = Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Bomba",
            sku="BM-1",
            id_unidad_medida_base=unidad,
            id_categoria=cat,
            id_moneda_precio=moneda_usd,
        )
        EntidadSincronizada.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="productos",
            id_externo="ext-prod-1",
            id_omni=str(prod.pk),
            checksum="old",
        )

        # Ejecutar outbound filtrado por ids en pagos, gestiones, contactos, productos
        for entidad, obj_id in (
            ("pagos", str(pago_c.pk)),
            ("gestiones_cobranza", str(g_cli.pk)),
            ("contactos", str(c_geo.pk)),
            ("productos", str(prod.pk)),
        ):
            job_f = JobSincronizacion.objects.create(
                id_instancia=fake_push_env,
                tipo_entidad=entidad,
                direccion="outbound",
                estado="pendiente",
                parametros={"ids": [obj_id]},
            )
            engine.ejecutar_job(job_f)
            job_f.refresh_from_db()
            assert job_f.estado in ("completado", "completado_con_errores")

        # Incremental (sin sync_completo ni ids, usando job previo completado para activar desde_eff)
        for entidad in ("pagos", "gestiones_cobranza", "contactos", "productos"):
            job_inc = JobSincronizacion.objects.create(
                id_instancia=fake_push_env,
                tipo_entidad=entidad,
                direccion="outbound",
                estado="pendiente",
            )
            engine.ejecutar_job(job_inc)

        # Entidad desconocida en bidireccional (aunque conector.supports sea True) -> fallido (líneas 114-117)
        job_unk = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="desconocida",
            direccion="bidireccional",
            estado="pendiente",
        )
        with patch.object(_FakePushConnector, "supports", return_value=True):
            engine.ejecutar_job(job_unk)
        job_unk.refresh_from_db()
        assert job_unk.estado == "fallido"

        # Entidad sin método push en outbound directo -> fallido
        job_no_push = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="inventario",
            direccion="outbound",
            estado="pendiente",
        )
        engine.ejecutar_job(job_no_push)
        job_no_push.refresh_from_db()
        assert job_no_push.estado == "fallido"

        # _preparar_items_push fallando -> job fallido
        job_prep_err = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
        )
        with patch.object(engine, "_preparar_items_push", side_effect=RuntimeError("db boom")):
            engine.ejecutar_job(job_prep_err)
        job_prep_err.refresh_from_db()
        assert job_prep_err.estado == "fallido"

        # ConnectorConnectionError aborta el push como fallido (pago fresco aún no mapeado)
        Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cli,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("12.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        job_conn_err = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
            parametros={"sync_completo": True},
        )
        with patch.object(_FakePushConnector, "push_pago_cobranza", side_effect=ConnectorConnectionError("down")):
            engine.ejecutar_job(job_conn_err)
        job_conn_err.refresh_from_db()
        assert job_conn_err.estado == "fallido"

        # Validación res_id <= 0 en push_gestion_cobranza
        with pytest.raises(ConnectorDataError, match="mayor que cero"):
            _odoo_conn({"push_habilitado": True}).push_gestion_cobranza({"partner_id": -5})

        # _ejecutar_push cuando el conector no implementa el método (p.ej. BaseConnector sin push)
        job_sin_metodo = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
        )
        conector_sin_metodo = MagicMock(spec=["supports", "instancia"])
        engine._ejecutar_push(job_sin_metodo, conector_sin_metodo, None, SyncResult("pagos"))
        job_sin_metodo.refresh_from_db()
        assert job_sin_metodo.estado == "fallido"

        # Resolvers adicionales vía asignaciones (id_cxc, id_factura_venta) y gestión (cxc / EntidadSincronizada)
        cxc_ext = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente_externo_id="odoo:91",
            cliente_externo_nombre="Ext",
            monto=Decimal("10.00"),
            fecha_emision=date(2026, 11, 1),
            fecha_vencimiento=date(2026, 11, 10),
            referencia_externa="odoo:out_invoice:910",
        )
        cxc_cli = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli,
            cliente_externo_nombre="Cli",
            monto=Decimal("10.00"),
            fecha_emision=date(2026, 11, 1),
            fecha_vencimiento=date(2026, 11, 10),
            referencia_externa="odoo:out_invoice:911",
        )
        pago_asig_cxc = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("10.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cli,
            id_pago=pago_asig_cxc,
            tipo_documento="CUENTA_POR_COBRAR",
            id_documento=cxc_ext.pk,
            id_cxc=cxc_ext,
            monto_asignado_pago=Decimal("10.00"),
            monto_asignado_documento=Decimal("10.00"),
            id_moneda_documento=moneda_usd,
        )
        assert engine._resolver_partner_odoo_de_pago(pago_asig_cxc, fake_push_env) == 91

        pago_asig_cli = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("10.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cli,
            id_pago=pago_asig_cli,
            tipo_documento="CUENTA_POR_COBRAR",
            id_documento=cxc_cli.pk,
            id_cxc=cxc_cli,
            monto_asignado_pago=Decimal("10.00"),
            monto_asignado_documento=Decimal("10.00"),
            id_moneda_documento=moneda_usd,
        )
        assert engine._resolver_partner_odoo_de_pago(pago_asig_cli, fake_push_env) == 71

        pago_asig_fv = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("10.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cli,
            id_pago=pago_asig_fv,
            tipo_documento="FACTURA_VENTA",
            id_documento=ff.pk,
            id_factura_venta=ff,
            monto_asignado_pago=Decimal("10.00"),
            monto_asignado_documento=Decimal("10.00"),
            id_moneda_documento=moneda_usd,
        )
        assert engine._resolver_partner_odoo_de_pago(pago_asig_fv, fake_push_env) == 71
        assert engine._resolver_facturas_odoo_de_pago(pago_asig_fv, fake_push_env) == [301]

        g_cxc_ext = GestionCobranza.objects.create(
            empresa=empresa_a,
            cxc=cxc_ext,
            canal="whatsapp",
            resultado="promesa_pago",
            fecha_gestion=date(2026, 11, 20),
        )
        assert engine._resolver_partner_odoo_de_gestion(g_cxc_ext, fake_push_env) == 91
        g_cxc_cli = GestionCobranza.objects.create(
            empresa=empresa_a,
            cxc=cxc_cli,
            canal="whatsapp",
            resultado="promesa_pago",
            fecha_gestion=date(2026, 11, 20),
        )
        assert engine._resolver_partner_odoo_de_gestion(g_cxc_cli, fake_push_env) == 71

        ent_uuid = str(uuid.uuid4())
        EntidadSincronizada.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            id_externo="92",
            id_omni=ent_uuid,
            activo=True,
        )
        g_ent = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id=ent_uuid,
            canal="email",
            resultado="contactado",
            fecha_gestion=date(2026, 11, 20),
        )
        assert engine._resolver_partner_odoo_de_gestion(g_ent, fake_push_env) == 92


# ── 7. Regresiones de Review PR-19 ───────────────────────────────────────────


class TestRegresionesReviewPR19:
    def test_watermark_inbound_no_bloquea_pago_local_en_outbound(self, fake_push_env, empresa_a, moneda_usd):
        """Caso 1: un sync inbound previo en T1 no impide empujar pago local preexistente sin sync_completo."""
        engine = SyncEngine()
        metodo = MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="Zelle", tipo_metodo="TRANSFERENCIA")
        contacto = Contacto.objects.create(id_empresa=empresa_a, nombre="Cli WM", es_cliente=True)
        EntidadSincronizada.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            id_externo="501",
            id_omni=str(contacto.pk),
            activo=True,
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("55.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
            referencia="REF-PRE-INBOUND",
        )
        t1 = timezone.now() + timedelta(minutes=5)
        JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="inbound",
            estado="completado",
            completado_en=t1,
        )

        job_out = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
            parametros={},
        )
        assert engine._calcular_desde(job_out, direccion_efectiva="outbound") is None
        res = engine.ejecutar_job(job_out)
        assert res.creados == 1
        assert res.fallidos == 0
        assert [p["id_omni"] for p in _FakePushConnector.pagos_llamados] == [str(pago.pk)]

        # Parámetro explícito 'desde' sigue filtrando registros más antiguos
        futuro = (timezone.now() + timedelta(days=1)).isoformat()
        job_explicit = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
            parametros={"desde": futuro},
        )
        res_exp = engine.ejecutar_job(job_explicit)
        assert res_exp.creados == 0

    def test_error_parcial_outbound_deja_registro_reintentable_sin_sync_completo(
        self, fake_push_env, empresa_a, moneda_usd
    ):
        """Caso 2: fallo parcial en outbound deja pago fallido reintentable en siguiente outbound sin sync_completo."""
        engine = SyncEngine()
        metodo = MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="Efectivo", tipo_metodo="EFECTIVO")
        contacto = Contacto.objects.create(id_empresa=empresa_a, nombre="Cli Retry", es_cliente=True)
        EntidadSincronizada.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            id_externo="502",
            id_omni=str(contacto.pk),
            activo=True,
        )
        pago_ok = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("20.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
            referencia="REF-OK-1",
        )
        pago_fail = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            fecha_pago=timezone.now(),
            monto=Decimal("30.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo,
            referencia="REF-FAIL-2",
        )

        _FakePushConnector.fail_on_id = str(pago_fail.pk)
        job_1 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
        )
        res_1 = engine.ejecutar_job(job_1)
        job_1.refresh_from_db()
        assert job_1.estado == "completado_con_errores"
        assert res_1.creados == 1
        assert res_1.fallidos == 1

        # En el siguiente outbound normal (sin sync_completo ni desde explícito), pago_fail se reintenta y pago_ok no se duplica
        _FakePushConnector.fail_on_id = None
        _FakePushConnector.pagos_llamados = []
        job_2 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="pagos",
            direccion="outbound",
            estado="pendiente",
        )
        res_2 = engine.ejecutar_job(job_2)
        job_2.refresh_from_db()
        assert job_2.estado == "completado"
        assert res_2.creados == 1
        assert res_2.fallidos == 0
        assert [p["id_omni"] for p in _FakePushConnector.pagos_llamados] == [str(pago_fail.pk)]
        assert EntidadSincronizada.objects.filter(
            id_instancia=fake_push_env, tipo_entidad="pagos", id_omni=str(pago_ok.pk)
        ).exists()
        assert EntidadSincronizada.objects.filter(
            id_instancia=fake_push_env, tipo_entidad="pagos", id_omni=str(pago_fail.pk)
        ).exists()

    def test_gestion_cliente_id_no_uuid_aisla_error_y_no_tumba_job(self, fake_push_env, empresa_a):
        """cliente_id inválido no-UUID se aísla por registro: procesa gestiones válidas y mantiene instancia activa."""
        engine = SyncEngine()
        contacto_ok = Contacto.objects.create(id_empresa=empresa_a, nombre="Cli Valido", es_cliente=True)
        EntidadSincronizada.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            id_externo="601",
            id_omni=str(contacto_ok.pk),
            activo=True,
        )
        g_bad = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id="not-a-uuid",
            canal="llamada",
            resultado="no_contesta",
            fecha_gestion=date(2026, 11, 20),
        )
        g_good = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id=str(contacto_ok.pk),
            canal="whatsapp",
            resultado="promesa_pago",
            fecha_gestion=date(2026, 11, 20),
        )
        assert engine._resolver_partner_odoo_de_gestion(g_bad, fake_push_env) is None

        job = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="gestiones_cobranza",
            direccion="outbound",
            estado="pendiente",
        )

        def _fake_push_gestion_strict(self_conn, datos: dict) -> str:
            if not datos.get("partner_id"):
                raise ConnectorDataError("Se requiere 'partner_id' para registrar gestión en Odoo.")
            self_conn.gestiones_llamadas.append(datos)
            _FakePushConnector.seq += 1
            return str(_FakePushConnector.seq)

        with patch.object(_FakePushConnector, "push_gestion_cobranza", _fake_push_gestion_strict):
            res = engine.ejecutar_job(job)
        job.refresh_from_db()
        fake_push_env.refresh_from_db()
        assert res.creados == 1
        assert res.fallidos == 1
        assert job.estado == "completado_con_errores"
        assert fake_push_env.estado == "activo"
        assert [g["id_omni"] for g in _FakePushConnector.gestiones_llamadas] == [str(g_good.pk)]
        assert LogDetalleSincronizacion.objects.filter(id_job=job, id_omni=str(g_bad.pk), operacion="error").exists()

        # Excepción inesperada en _preparar_items_push también queda aislada por registro
        g_good2 = GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id=str(contacto_ok.pk),
            canal="email",
            resultado="contactado",
            fecha_gestion=date(2026, 11, 20),
        )
        with patch.object(engine, "_resolver_partner_odoo_de_gestion", side_effect=[RuntimeError("boom"), 601, 601]):
            _FakePushConnector.gestiones_llamadas = []
            job_prep = JobSincronizacion.objects.create(
                id_instancia=fake_push_env,
                tipo_entidad="gestiones_cobranza",
                direccion="outbound",
                estado="pendiente",
                parametros={"sync_completo": True},
            )
            res_prep = engine.ejecutar_job(job_prep)
        job_prep.refresh_from_db()
        fake_push_env.refresh_from_db()
        assert res_prep.creados == 1
        assert res_prep.omitidos == 1
        assert res_prep.fallidos == 1
        assert job_prep.estado == "completado_con_errores"
        assert fake_push_env.estado == "activo"
        assert [g["id_omni"] for g in _FakePushConnector.gestiones_llamadas] == [str(g_good2.pk)]

    def test_bidireccional_contactos_y_productos_sin_loop_checksum(self, fake_push_env, empresa_a, moneda_usd):
        """Dos corridas bidireccionales consecutivas no deben sobrescribir checksum pull ni generar ping-pong."""
        engine = SyncEngine()
        Contacto.objects.create(id_empresa=empresa_a, nombre="Local C Loop", email="lc@a.com", es_cliente=True)
        _FakePushConnector.pull_data = [
            {"id_externo": "ext-c-1", "nombre": "Ext C Loop", "email": "ec@a.com", "_checksum": "pull-c-v1"}
        ]

        job_c1 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            direccion="bidireccional",
            estado="pendiente",
        )
        res_c1 = engine.ejecutar_job(job_c1)
        assert res_c1.creados == 2  # 1 pull + 1 push local
        assert res_c1.actualizados == 1  # push del contacto recién importado
        map_ext_c = EntidadSincronizada.objects.get(
            id_instancia=fake_push_env, tipo_entidad="contactos", id_externo="ext-c-1"
        )
        assert map_ext_c.checksum == "pull-c-v1"
        assert map_ext_c.metadatos.get("hash_datos_push")

        # Segunda corrida bidireccional (incluso con sync_completo=True): 0 cambios, todo omitido
        _FakePushConnector.contactos_llamados = []
        job_c2 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="contactos",
            direccion="bidireccional",
            estado="pendiente",
            parametros={"sync_completo": True},
        )
        res_c2 = engine.ejecutar_job(job_c2)
        assert res_c2.creados == 0
        assert res_c2.actualizados == 0
        assert res_c2.omitidos >= 3  # 1 pull omitido + 2 push omitidos
        assert _FakePushConnector.contactos_llamados == []

        # Productos bidireccional sin ping-pong
        unidad = UnidadMedida.objects.create(id_empresa=empresa_a, nombre="Pza", abreviatura="PZA", tipo="CANTIDAD")
        cat = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="General Loop")
        Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Prod Local Loop",
            sku="PL-1",
            id_unidad_medida_base=unidad,
            id_categoria=cat,
            id_moneda_precio=moneda_usd,
        )
        _FakePushConnector.pull_productos_data = [
            {
                "id_externo": "ext-p-1",
                "nombre": "Prod Ext Loop",
                "codigo_interno": "PE-1",
                "precio_venta": Decimal("10.00"),
                "_checksum": "pull-p-v1",
            }
        ]
        job_p1 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="productos",
            direccion="bidireccional",
            estado="pendiente",
        )
        res_p1 = engine.ejecutar_job(job_p1)
        assert res_p1.creados >= 2
        map_ext_p = EntidadSincronizada.objects.get(
            id_instancia=fake_push_env, tipo_entidad="productos", id_externo="ext-p-1"
        )
        assert map_ext_p.checksum == "pull-p-v1"
        assert map_ext_p.metadatos.get("hash_datos_push")

        _FakePushConnector.productos_llamados = []
        job_p2 = JobSincronizacion.objects.create(
            id_instancia=fake_push_env,
            tipo_entidad="productos",
            direccion="bidireccional",
            estado="pendiente",
            parametros={"sync_completo": True},
        )
        res_p2 = engine.ejecutar_job(job_p2)
        assert res_p2.creados == 0
        assert res_p2.actualizados == 0
        assert res_p2.omitidos >= 3
        assert _FakePushConnector.productos_llamados == []
