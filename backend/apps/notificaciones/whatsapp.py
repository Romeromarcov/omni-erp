"""Adaptador seguro de WhatsApp Business Cloud API y Chatter documental (Plan 09 Fase 8.1)."""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any

import requests

from apps.core.exceptions import DomainError

from .models import CanalNotificacion, MensajeChatterDocumento

logger = logging.getLogger("apps.notificaciones.whatsapp")

_DIGITS_RE = re.compile(r"\D+")


class WhatsAppBusinessError(DomainError):
    """Error controlado al validar o despachar mensajes WhatsApp Business."""


def normalizar_telefono_e164(telefono: str) -> str:
    """Normaliza un número telefónico a formato ``+<digitos>`` (7 a 15 dígitos)."""
    raw = str(telefono or "").strip()
    if "\x00" in raw or any(ord(ch) < 32 for ch in raw):
        raise WhatsAppBusinessError("Número telefónico inválido.")
    digits = _DIGITS_RE.sub("", raw)
    if len(digits) < 7 or len(digits) > 15:
        raise WhatsAppBusinessError("El número WhatsApp debe tener entre 7 y 15 dígitos (ej. +584141234567).")
    return f"+{digits}"


def construir_mensaje_plantilla(plantilla: str, contexto: dict[str, Any] | None = None) -> str:
    """Construye el texto saliente para cotización, cobranza, tracking o mensaje libre."""
    ctx = contexto or {}
    modo = (plantilla or "libre").strip().lower()
    if modo == "cotizacion":
        num = ctx.get("numero", "S/N")
        cliente = ctx.get("cliente", "Cliente")
        monto = ctx.get("monto", "")
        moneda = ctx.get("moneda", "USD")
        url_pdf = ctx.get("pdf_url", "")
        return (
            f"Estimado(a) {cliente}, compartimos su Cotización #{num} por {monto} {moneda}. "
            f"{f'Descargar: {url_pdf}' if url_pdf else ''}"
        ).strip()
    if modo == "cobranza":
        cliente = ctx.get("cliente", "Cliente")
        num = ctx.get("numero", "documento")
        saldo = ctx.get("saldo", "")
        moneda = ctx.get("moneda", "USD")
        return f"Hola {cliente}, recordatorio amable sobre su saldo pendiente de {saldo} {moneda} ({num}).".strip()
    if modo == "tracking":
        num = ctx.get("numero", "Despacho")
        estado = ctx.get("estado", "EN_RUTA")
        url_track = ctx.get("tracking_url", "")
        return f"Su pedido {num} se encuentra {estado}. {f'Seguimiento en vivo: {url_track}' if url_track else ''}".strip()
    cuerpo = str(ctx.get("mensaje") or ctx.get("cuerpo") or "").strip()
    if not cuerpo:
        raise WhatsAppBusinessError("Debe indicar el cuerpo del mensaje o una plantilla válida.")
    return cuerpo


def enviar_whatsapp_documento(
    *,
    empresa,
    tipo_documento: str,
    documento_id: uuid.UUID,
    telefono: str,
    cuerpo: str = "",
    plantilla: str = "libre",
    contexto: dict[str, Any] | None = None,
    autor=None,
) -> MensajeChatterDocumento:
    """Registra en el chatter del documento y despacha por WhatsApp Business Cloud API (o modo SIMULADO)."""
    if tipo_documento not in dict(MensajeChatterDocumento.TIPOS_DOCUMENTO):
        raise WhatsAppBusinessError("Tipo de documento no soportado para WhatsApp Business.")

    tel_norm = normalizar_telefono_e164(telefono)
    ctx_full = dict(contexto or {})
    if cuerpo.strip():
        ctx_full.setdefault("mensaje", cuerpo.strip())
    texto_final = cuerpo.strip() or construir_mensaje_plantilla(plantilla, ctx_full)

    token = os.environ.get("WHATSAPP_CLOUD_TOKEN", "").strip()
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_base = os.environ.get("WHATSAPP_CLOUD_API_URL", "https://graph.facebook.com/v20.0").rstrip("/")

    estado_envio = "SIMULADO"
    provider_id = f"wamid.sim.{uuid.uuid4().hex[:12]}"
    metadata: dict[str, Any] = {
        "modo": "SIMULADO",
        "plantilla": plantilla,
        "telefono_destino": tel_norm,
    }

    if token and phone_id:
        endpoint = f"{api_base}/{phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": tel_norm.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": texto_final[:4096]},
        }
        try:
            resp = requests.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=10,
            )
            if 200 <= resp.status_code < 300:
                body_resp = resp.json() if resp.content else {}
                msgs = body_resp.get("messages") or []
                provider_id = (
                    str(msgs[0].get("id")) if msgs and isinstance(msgs[0], dict) else f"wamid.{uuid.uuid4().hex[:10]}"
                )
                estado_envio = "ENVIADO"
                metadata["modo"] = "CLOUD_API"
            else:
                estado_envio = "FALLIDO"
                provider_id = ""
                metadata["modo"] = "CLOUD_API"
                metadata["http_status"] = resp.status_code
        except requests.RequestException as exc:
            logger.warning(
                "whatsapp cloud api error | empresa=%s | doc=%s | err=%s",
                empresa.pk,
                documento_id,
                exc.__class__.__name__,
            )
            estado_envio = "FALLIDO"
            provider_id = ""
            metadata["modo"] = "CLOUD_API"
            metadata["error"] = exc.__class__.__name__

    return MensajeChatterDocumento.objects.create(
        id_empresa=empresa,
        tipo_documento=tipo_documento,
        documento_id=documento_id,
        autor=autor,
        canal=CanalNotificacion.WHATSAPP,
        es_nota_interna=False,
        destinatario_telefono=tel_norm,
        cuerpo=texto_final,
        estado_envio=estado_envio,
        provider_message_id=provider_id,
        metadata_json=metadata,
    )
