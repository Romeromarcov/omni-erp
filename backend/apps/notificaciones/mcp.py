"""Herramientas MCP de ``apps/notificaciones`` — Chatter documental y WhatsApp Business (Plan 09 Fase 8.1)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
from typing import Any
import uuid

from apps.core.exceptions import sanitize_mcp_error

logger = logging.getLogger("omni.mcp.notificaciones")

_SCOPE = "notificaciones"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _parse_uuid(valor: str, campo: str) -> uuid.UUID:
    raw = str(valor)
    if "\x00" in raw:
        raise ValueError(f"{campo} inválido.")
    return uuid.UUID(raw.strip())


def notificaciones_listar_chatter_documento(
    capability_token: str,
    empresa_id: str,
    tipo_documento: str,
    documento_id: str,
) -> dict[str, Any]:
    """Lista los mensajes del chatter y envíos WhatsApp de un documento. Scope requerido: ``notificaciones:read``."""
    from apps.core.models import Empresa  # noqa: PLC0415
    from apps.notificaciones.models import MensajeChatterDocumento  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            doc_uuid = _parse_uuid(documento_id, "documento_id")
        except (ValueError, TypeError):
            return {"error": "documento_id no es un UUID válido."}
        tipo_clean = str(tipo_documento or "").strip().upper()
        if "\x00" in tipo_clean or tipo_clean not in dict(MensajeChatterDocumento.TIPOS_DOCUMENTO):
            return {"error": "tipo_documento inválido."}

        empresa = Empresa.objects.filter(pk=uuid.UUID(str(ctx["empresa_id"])), activo=True).first()
        if empresa is None:
            return {"error": "Empresa inactiva o no encontrada."}

        qs = (
            MensajeChatterDocumento.objects.filter(
                id_empresa=empresa,
                tipo_documento=tipo_clean,
                documento_id=doc_uuid,
                activo=True,
            )
            .select_related("autor")
            .order_by("-fecha_creacion")[:50]
        )
        return {
            "empresa_id": str(empresa.pk),
            "mensajes": [
                {
                    "id_mensaje": str(m.pk),
                    "canal": m.canal,
                    "es_nota_interna": m.es_nota_interna,
                    "destinatario_telefono": m.destinatario_telefono,
                    "cuerpo": m.cuerpo,
                    "estado_envio": m.estado_envio,
                    "fecha_creacion": m.fecha_creacion.isoformat(),
                }
                for m in qs
            ],
        }


def notificaciones_enviar_whatsapp_documento(
    capability_token: str,
    empresa_id: str,
    tipo_documento: str,
    documento_id: str,
    telefono: str,
    plantilla: str = "libre",
    cuerpo: str = "",
) -> dict[str, Any]:
    """Despacha un mensaje WhatsApp Business ligado a un documento (modo SIMULADO si falta token Cloud). Scope: ``notificaciones:write``."""
    from apps.core.models import CapabilityToken, Empresa  # noqa: PLC0415
    from apps.notificaciones.whatsapp import WhatsAppBusinessError, enviar_whatsapp_documento  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        try:
            doc_uuid = _parse_uuid(documento_id, "documento_id")
        except (ValueError, TypeError):
            return {"error": "documento_id no es un UUID válido."}

        empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
        empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
        if empresa is None:
            return {"error": "Empresa inactiva o no encontrada."}

        token_obj = (
            CapabilityToken.objects.select_related("creado_por")
            .filter(token=capability_token, empresa=empresa, activo=True)
            .first()
        )
        autor = token_obj.creado_por if token_obj is not None else None
        try:
            msg = enviar_whatsapp_documento(
                empresa=empresa,
                tipo_documento=str(tipo_documento or "").strip().upper(),
                documento_id=doc_uuid,
                telefono=telefono,
                cuerpo=cuerpo,
                plantilla=plantilla,
                autor=autor,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="notificaciones_enviar_whatsapp_documento",
                    controlled_types=(WhatsAppBusinessError, ValueError),
                )
            }
        return {
            "id_mensaje": str(msg.pk),
            "estado_envio": msg.estado_envio,
            "destinatario_telefono": msg.destinatario_telefono,
            "provider_message_id": msg.provider_message_id,
        }


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": notificaciones_listar_chatter_documento,
        "name": "notificaciones_listar_chatter_documento",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": notificaciones_enviar_whatsapp_documento,
        "name": "notificaciones_enviar_whatsapp_documento",
        "scope": f"{_SCOPE}:write",
    },
]
