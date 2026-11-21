"""
Test de integración en vivo (opt-in) contra Odoo QA para Push Outbound (PR-19 / CTF-011).

Se omite por defecto salvo cuando ``ODOO_QA_LIVE_TEST=1``.
Lee credenciales exclusivamente desde variables de entorno; no contiene URLs,
usuarios ni llaves en código ni comentarios.
"""

from __future__ import annotations

import os
import uuid

import pytest

from apps.core.models import Empresa
from apps.integration_hub.connectors.odoo.connector import OdooConnector
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ODOO_QA_LIVE_TEST") != "1",
        reason="Live Odoo QA test is opt-in",
    ),
]


def _build_live_connector() -> OdooConnector:
    url = os.environ["ODOO_QA_URL"]
    db = os.environ.get("ODOO_QA_DB", "")
    user = os.environ["ODOO_QA_USER"]
    api_key = os.environ["ODOO_QA_API_KEY"]

    empresa = Empresa.objects.create(nombre_legal="Empresa QA Live")
    proveedor, _ = ConectorProveedor.objects.get_or_create(
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
    instancia = ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        nombre=f"Odoo QA Live {uuid.uuid4().hex[:8]}",
        estado="activo",
        configuracion={
            "host": url,
            "db": db,
            "user": user,
            "api_key": api_key,
            "push_habilitado": True,
            "push_modo_pago": "borrador",
        },
        entidades_activas=["facturas_compra", "pagos", "gestiones_cobranza"],
    )
    return OdooConnector(instancia)


def test_odoo_qa_live_outbound_push_y_lecturas():
    connector = _build_live_connector()

    # 1. Conexión y autenticación
    res_conn = connector.test_connection()
    assert res_conn.success is True, res_conn.message
    assert res_conn.version

    # 2. Lecturas inbound básicas (facturas_compra y pagos)
    facturas_compra = connector.pull_facturas_compra(limite=5)
    assert isinstance(facturas_compra, list)
    pagos = connector.pull_pagos(limite=5)
    assert isinstance(pagos, list)

    client = connector._get_write_client()
    socios = client.get_socios(limite=1)
    assert socios, "La instancia QA debe tener al menos un socio para la prueba."
    partner_id = int(socios[0]["id"])

    diarios = client.get_diarios(["bank", "cash"])
    assert diarios, "La instancia QA debe tener al menos un diario bank/cash."
    journal_id = int(diarios[0]["id"])

    # 3. push_pago_cobranza idempotente en modo borrador + limpieza unlink
    pago_key = f"QA-LIVE-PAGO-{uuid.uuid4().hex[:12]}"
    pago_id_1: str | None = None
    try:
        payload_pago = {
            "idempotency_key": pago_key,
            "partner_id": partner_id,
            "monto": "1.00",
            "journal_id": journal_id,
            "tipo": "cliente",
            "referencia": "Prueba QA idempotente borrador",
            "push_modo_pago": "borrador",
        }
        pago_id_1 = connector.push_pago_cobranza(payload_pago)
        assert pago_id_1.isdigit()
        pago_id_2 = connector.push_pago_cobranza(payload_pago)
        assert pago_id_2 == pago_id_1
    finally:
        if pago_id_1 and pago_id_1.isdigit():
            try:
                client.call("account.payment", "unlink", [[int(pago_id_1)]])
            except Exception:
                pass

    # 4. push_gestion_cobranza idempotente + limpieza best-effort (ACL-safe)
    gestion_key = f"QA-LIVE-GEST-{uuid.uuid4().hex[:12]}"
    msg_id_1: str | None = None
    try:
        payload_gestion = {
            "idempotency_key": gestion_key,
            "partner_id": partner_id,
            "cliente_nombre": "Cliente QA",
            "orden_ref": "QA-REF-001",
            "canal": "whatsapp",
            "resultado": "contactado",
            "notas": "Nota de prueba automática <verificada> & segura",
            "fecha_gestion": "2026-11-20",
        }
        msg_id_1 = connector.push_gestion_cobranza(payload_gestion)
        assert msg_id_1.isdigit()
        msg_id_2 = connector.push_gestion_cobranza(payload_gestion)
        assert msg_id_2 == msg_id_1
    finally:
        if msg_id_1 and msg_id_1.isdigit():
            try:
                client.call("mail.message", "unlink", [[int(msg_id_1)]])
            except Exception:
                pass
