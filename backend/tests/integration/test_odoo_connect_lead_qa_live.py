"""
Smoke test controlado de integración en vivo (opt-in) contra Odoo QA para el
flujo Omni Connect ``EventoOutbox`` -> ``crm.lead`` (Ola 6 / PR-35).

Se omite por defecto salvo cuando ``ODOO_QA_LIVE_TEST=1``.
Lee credenciales exclusivamente desde variables de entorno; nunca contiene URLs,
usuarios ni llaves reales en código ni comentarios, y rechaza explícitamente
cualquier host no etiquetado como QA/staging/test/sandbox/local.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import pytest

from apps.core.models import Empresa
from apps.integration_hub.connectors.odoo.connector import OdooConnector
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor, EntidadSincronizada, EventoOutbox
from apps.integration_hub.outbox import (
    ENTIDAD_CRM_LEAD,
    EVENTO_CRM_LEAD_ANONIMIZADO,
    EVENTO_CRM_LEAD_CAPTURADO,
    EVENTO_CRM_LEAD_ETAPA_CAMBIADA,
    despachar_lote_outbox,
    encolar_evento_outbox,
)
from tests.connect.builders import consentimiento, crear_etapa, crear_lead, crear_pipeline

_QA_HOST_TOKENS = ("qa", "staging", "test", "sandbox", "localhost", "127.0.0.1")


def _assert_host_es_qa_no_prod(url: str) -> None:
    """Guard fail-closed: bloquea cualquier host sin indicador explícito de QA/test."""
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        raise ValueError("La URL de Odoo QA debe incluir esquema http/https y hostname válido.")
    if not any(tok in host for tok in _QA_HOST_TOKENS):
        raise ValueError("Guard de seguridad: el hostname destino no corresponde a un entorno QA/staging/test/local.")


@pytest.mark.unit
def test_guardia_rechaza_host_produccion():
    _assert_host_es_qa_no_prod("https://odoo-qa.example.invalid")
    _assert_host_es_qa_no_prod("http://localhost:8069")

    for url_bloqueada in (
        "",
        "ftp://odoo-qa.example.invalid",
        "https://erp.example.invalid",
        "https://prod.example.invalid",
    ):
        with pytest.raises(ValueError):
            _assert_host_es_qa_no_prod(url_bloqueada)


def _crear_conector_qa(empresa: Empresa) -> tuple[OdooConnector, ConectorInstancia]:
    url = os.environ["ODOO_QA_URL"]
    _assert_host_es_qa_no_prod(url)

    db = os.environ.get("ODOO_QA_DB", "")
    user = os.environ["ODOO_QA_USER"]
    api_key = os.environ["ODOO_QA_API_KEY"]
    write_user = os.environ.get("ODOO_QA_WRITE_USER") or user
    write_api_key = os.environ.get("ODOO_QA_WRITE_API_KEY") or api_key

    proveedor, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo",
        defaults={
            "nombre": "Odoo",
            "estado": "activo",
            "capacidades": ["contactos", "productos", "pagos", "gestiones_cobranza"],
        },
    )
    instancia = ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        nombre=f"Odoo QA Connect {uuid.uuid4().hex[:8]}",
        estado="activo",
        configuracion={
            "host": url,
            "db": db,
            "user": user,
            "api_key": api_key,
            "write_user": write_user,
            "write_api_key": write_api_key,
            "empujar_connect_leads": True,
        },
        entidades_activas=["contactos"],
    )
    return OdooConnector(instancia), instancia


@pytest.mark.django_db
@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("ODOO_QA_LIVE_TEST") != "1",
    reason="Live Odoo QA test is opt-in",
)
def test_odoo_qa_live_connect_outbox_crm_lead_lifecycle():
    empresa = Empresa.objects.create(nombre_legal=f"Empresa QA Connect {uuid.uuid4().hex[:6]}")
    connector, instancia = _crear_conector_qa(empresa)
    client = connector._get_connect_lead_write_client()

    marker = f"QA-CONNECT-{uuid.uuid4().hex[:10].upper()}"
    email_unico = f"{marker.lower()}@example.invalid"

    pipeline = crear_pipeline(empresa, nombre="Pipeline QA Live", es_predeterminado=True)
    etapa_1 = crear_etapa(empresa, pipeline=pipeline, nombre="Nuevo", orden=1)
    etapa_2 = crear_etapa(empresa, pipeline=pipeline, nombre="Calificado", orden=2)
    lead = crear_lead(
        empresa,
        pipeline=pipeline,
        etapa=etapa_1,
        nombre=marker,
        apellido="SmokeTest",
        empresa_nombre=f"Empresa {marker}",
        email=email_unico,
        telefono="+584140000000",
        fuente="CONNECT",
        mensaje=f"Mensaje inicial {marker}",
        **consentimiento(),
    )

    odoo_lead_id: int | None = None
    try:
        # 1. Captura inicial -> crea crm.lead en Odoo QA + EntidadSincronizada
        ev_captura = encolar_evento_outbox(
            empresa,
            tipo_evento=EVENTO_CRM_LEAD_CAPTURADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead.pk,
            clave_idempotencia=f"qa-captura-{lead.pk}",
        )
        res_1 = despachar_lote_outbox(limite=10)
        assert res_1["enviados"] >= 1
        assert res_1["fallidos"] == 0
        assert res_1["dlq"] == 0

        ev_captura.refresh_from_db()
        assert ev_captura.estado == EventoOutbox.Estado.ENVIADO, ev_captura.ultimo_error

        mapeo = EntidadSincronizada.objects.get(
            id_instancia=instancia,
            tipo_entidad="crm_lead",
            id_omni=str(lead.pk),
        )
        assert mapeo.id_externo.isdigit()
        odoo_lead_id = int(mapeo.id_externo)

        leido_1 = client.call(
            "crm.lead",
            "search_read",
            [[["id", "=", odoo_lead_id]]],
            {"fields": ["id", "name", "email_from", "description", "partner_id"]},
        )
        assert len(leido_1) == 1
        assert leido_1[0]["email_from"] == email_unico
        assert f"[OMNI-LEAD:{lead.pk}]" in (leido_1[0].get("description") or "")

        # 2. Cambio de etapa -> actualización idempotente sobre el MISMO crm.lead
        lead.etapa = etapa_2
        lead.save(update_fields=["etapa", "fecha_actualizacion"])
        ev_etapa = encolar_evento_outbox(
            empresa,
            tipo_evento=EVENTO_CRM_LEAD_ETAPA_CAMBIADA,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead.pk,
            clave_idempotencia=f"qa-etapa-{lead.pk}",
        )
        res_2 = despachar_lote_outbox(limite=10)
        assert res_2["enviados"] >= 1
        assert res_2["fallidos"] == 0

        ev_etapa.refresh_from_db()
        assert ev_etapa.estado == EventoOutbox.Estado.ENVIADO, ev_etapa.ultimo_error

        por_tag = client.call(
            "crm.lead",
            "search",
            [[["description", "ilike", f"[OMNI-LEAD:{lead.pk}]"]]],
            {"limit": 10},
        )
        assert por_tag == [odoo_lead_id]

        # 3. Anonimización -> limpia PII en el MISMO crm.lead sin crear registro nuevo
        lead.nombre = "Anonimizado"
        lead.apellido = ""
        lead.email = ""
        lead.telefono = ""
        lead.save(update_fields=["nombre", "apellido", "email", "telefono", "fecha_actualizacion"])
        ev_anon = encolar_evento_outbox(
            empresa,
            tipo_evento=EVENTO_CRM_LEAD_ANONIMIZADO,
            entidad_tipo=ENTIDAD_CRM_LEAD,
            entidad_id=lead.pk,
            clave_idempotencia=f"qa-anon-{lead.pk}",
        )
        res_3 = despachar_lote_outbox(limite=10)
        assert res_3["enviados"] >= 1
        assert res_3["fallidos"] == 0

        ev_anon.refresh_from_db()
        assert ev_anon.estado == EventoOutbox.Estado.ENVIADO, ev_anon.ultimo_error

        leido_anon = client.call(
            "crm.lead",
            "search_read",
            [[["id", "=", odoo_lead_id]]],
            {"fields": ["id", "name", "email_from", "phone", "partner_name", "description"]},
        )
        assert len(leido_anon) == 1
        assert leido_anon[0]["name"] == "Contacto anonimizado"
        assert leido_anon[0]["email_from"] is False

        # 4. Garantía estricta: 0 escrituras en res.partner
        partners_email = client.call(
            "res.partner",
            "search_read",
            [[["email", "=", email_unico]]],
            {"fields": ["id", "name", "email"], "limit": 5},
        )
        partners_name = client.call(
            "res.partner",
            "search_read",
            [[["name", "ilike", marker]]],
            {"fields": ["id", "name", "email"], "limit": 5},
        )
        assert partners_email == []
        assert partners_name == []
    finally:
        if odoo_lead_id is not None:
            try:
                client.call("crm.lead", "unlink", [[odoo_lead_id]])
            except Exception:
                pass
