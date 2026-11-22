"""Cola transaccional Outbox multi-tenant y dispatcher idempotente (Omni Connect S7–S9)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import rls
from apps.core.exceptions import _UNSAFE_TRACE_PATTERNS, DomainError
from apps.core.models import Empresa
from apps.core.uuid import uuid7
from apps.integration_hub.connectors.odoo.client import sanitizar_error_odoo
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import ConectorInstancia, EventoOutbox

logger = logging.getLogger(__name__)

ENTIDAD_CRM_LEAD = "crm.Lead"

EVENTO_CRM_LEAD_CAPTURADO = "crm.lead.capturado"
EVENTO_CRM_LEAD_ACTUALIZADO = "crm.lead.actualizado"
EVENTO_CRM_LEAD_ETAPA_CAMBIADA = "crm.lead.etapa_cambiada"
EVENTO_CRM_LEAD_CONVERTIDO = "crm.lead.convertido"
EVENTO_CRM_LEAD_ANONIMIZADO = "crm.lead.anonimizado"

EVENTOS_CRM_LEAD = frozenset(
    {
        EVENTO_CRM_LEAD_CAPTURADO,
        EVENTO_CRM_LEAD_ACTUALIZADO,
        EVENTO_CRM_LEAD_ETAPA_CAMBIADA,
        EVENTO_CRM_LEAD_CONVERTIDO,
        EVENTO_CRM_LEAD_ANONIMIZADO,
    }
)

OUTBOX_BACKOFF_BASE_SEGUNDOS = 60
OUTBOX_BACKOFF_MAX_SEGUNDOS = 3600
_SECRET_CONFIG_KEYS = ("api_key", "write_api_key", "password", "token", "secret")


class OutboxError(DomainError):
    """Error de dominio controlado para operaciones sobre la cola Outbox."""


def calcular_backoff_segundos(
    intentos: int,
    *,
    base_segundos: int = OUTBOX_BACKOFF_BASE_SEGUNDOS,
    max_segundos: int = OUTBOX_BACKOFF_MAX_SEGUNDOS,
) -> int:
    """Calcula backoff exponencial acotado: ``min(base * 2**(intentos - 1), max)``."""
    exponente = max(0, int(intentos) - 1)
    return min(int(base_segundos) * (2**exponente), int(max_segundos))


def sanitizar_error_outbox(exc_or_msg: Any, *, secrets: Iterable[str] = ()) -> str:
    """Sanitiza y trunca el error persistido en ``EventoOutbox.ultimo_error`` (R-CODE-8)."""
    limpio = sanitizar_error_odoo(exc_or_msg, secrets=secrets).replace("\x00", "").strip()
    if not limpio or any(patron.search(limpio) for patron in _UNSAFE_TRACE_PATTERNS):
        return "Error despachando evento outbox."
    return limpio[:500]


def _parsear_uuid(valor: uuid.UUID | str, campo: str) -> uuid.UUID:
    if isinstance(valor, uuid.UUID):
        return valor
    texto = str(valor or "")
    if "\x00" in texto:
        raise DjangoValidationError({campo: "El identificador contiene caracteres inválidos."})
    try:
        return uuid.UUID(texto.strip())
    except (ValueError, TypeError) as exc:
        raise DjangoValidationError({campo: f"'{valor}' no es un UUID válido."}) from exc


@transaction.atomic
def encolar_evento_outbox(
    empresa: Empresa,
    *,
    tipo_evento: str,
    entidad_tipo: str,
    entidad_id: uuid.UUID | str,
    payload: dict[str, Any] | None = None,
    clave_idempotencia: str | None = None,
    max_intentos: int = 5,
    proximo_intento_en: datetime | None = None,
) -> EventoOutbox:
    """Inserta o reutiliza idempotentemente un ``EventoOutbox`` dentro de la transacción activa."""
    entidad_uuid = _parsear_uuid(entidad_id, "entidad_id")
    tipo_limpio = str(tipo_evento or "").strip()
    entidad_tipo_limpia = str(entidad_tipo or "").strip()

    if clave_idempotencia is not None and str(clave_idempotencia).strip():
        clave = str(clave_idempotencia).strip()
    else:
        clave = f"{tipo_limpio}:{entidad_tipo_limpia}:{entidad_uuid}:{uuid7()}"[:120]

    existente = EventoOutbox.objects.filter(
        id_empresa=empresa,
        clave_idempotencia=clave,
    ).first()
    if existente is not None:
        return existente

    evento = EventoOutbox(
        id_empresa=empresa,
        tipo_evento=tipo_limpio,
        entidad_tipo=entidad_tipo_limpia,
        entidad_id=entidad_uuid,
        clave_idempotencia=clave,
        payload=dict(payload or {}),
        estado=EventoOutbox.Estado.PENDIENTE,
        intentos=0,
        max_intentos=max_intentos,
        proximo_intento_en=proximo_intento_en or timezone.now(),
    )
    evento.full_clean()

    try:
        with transaction.atomic():
            evento.save()
        return evento
    except IntegrityError:
        concurrente = EventoOutbox.objects.filter(
            id_empresa=empresa,
            clave_idempotencia=clave,
        ).first()
        if concurrente is not None:
            return concurrente
        raise


@transaction.atomic
def reintentar_evento_outbox(
    evento_id: uuid.UUID | str,
    *,
    empresa_ids: Sequence[uuid.UUID],
) -> EventoOutbox:
    """Reencola un evento en ``FALLIDO`` o ``DLQ`` hacia ``PENDIENTE`` con ``intentos=0``."""
    try:
        evento_uuid = _parsear_uuid(evento_id, "evento_id")
    except DjangoValidationError as exc:
        raise OutboxError("Identificador de evento outbox inválido.") from exc

    evento = (
        EventoOutbox.objects.select_for_update()
        .filter(
            pk=evento_uuid,
            id_empresa_id__in=list(empresa_ids),
            activo=True,
        )
        .first()
    )
    if evento is None:
        raise OutboxError("Evento outbox no encontrado en las empresas autorizadas.")

    if evento.estado not in (EventoOutbox.Estado.FALLIDO, EventoOutbox.Estado.DLQ):
        raise OutboxError(
            f"Solo se pueden reintentar eventos en estado FALLIDO o DLQ (estado actual: {evento.estado})."
        )

    evento.estado = EventoOutbox.Estado.PENDIENTE
    evento.intentos = 0
    evento.proximo_intento_en = timezone.now()
    evento.procesado_en = None
    evento.ultimo_error = ""
    evento.full_clean()
    evento.save(
        update_fields=[
            "estado",
            "intentos",
            "proximo_intento_en",
            "procesado_en",
            "ultimo_error",
            "fecha_actualizacion",
        ]
    )
    return evento


def _destinos_opt_in_evento(evento: EventoOutbox) -> list[ConectorInstancia]:
    """Retorna conectores activos de la empresa con opt-in explícito para el tipo de evento."""
    if evento.tipo_evento not in EVENTOS_CRM_LEAD and evento.entidad_tipo != ENTIDAD_CRM_LEAD:
        return []

    instancias = list(
        ConectorInstancia.objects.select_related("id_proveedor")
        .filter(
            id_empresa_id=evento.id_empresa_id,
            activo=True,
            id_proveedor__codigo="odoo",
        )
        .exclude(estado="inactivo")
        .order_by("fecha_creacion")
    )
    return [inst for inst in instancias if inst.get_config().get("empujar_connect_leads") is True]


def _secretos_instancias(instancias: Iterable[ConectorInstancia]) -> list[str]:
    secretos: list[str] = []
    for inst in instancias:
        cfg = inst.get_config()
        for clave in _SECRET_CONFIG_KEYS:
            val = cfg.get(clave)
            if isinstance(val, str) and val.strip():
                secretos.append(val.strip())
    return secretos


def despachar_lote_outbox(
    limite: int = 50,
    ahora: datetime | None = None,
) -> dict[str, int]:
    """Despacha un lote de eventos elegibles respetando RLS por tenant y ``SKIP LOCKED``."""
    ahora_ref = ahora or timezone.now()
    tope = max(1, min(int(limite), 500))

    with rls.rls_bypass():
        candidatos = list(
            EventoOutbox.objects.filter(
                activo=True,
                estado__in=[EventoOutbox.Estado.PENDIENTE, EventoOutbox.Estado.FALLIDO],
                proximo_intento_en__lte=ahora_ref,
            )
            .order_by("proximo_intento_en", "fecha_creacion")
            .values_list("id_empresa_id", "id_evento")[:tope]
        )

    enviados = 0
    sin_destino = 0
    fallidos = 0
    dlq = 0
    omitidos_bloqueo = 0

    for empresa_id, evento_id in candidatos:
        with rls.rls_tenant_context([empresa_id]):
            with transaction.atomic():
                evento = (
                    EventoOutbox.objects.select_for_update(skip_locked=True)
                    .filter(
                        pk=evento_id,
                        id_empresa_id=empresa_id,
                        activo=True,
                        estado__in=[EventoOutbox.Estado.PENDIENTE, EventoOutbox.Estado.FALLIDO],
                        proximo_intento_en__lte=ahora_ref,
                    )
                    .first()
                )
                if evento is None:
                    omitidos_bloqueo += 1
                    continue

                evento.estado = EventoOutbox.Estado.PROCESANDO
                evento.save(update_fields=["estado", "fecha_actualizacion"])

                destinos = _destinos_opt_in_evento(evento)
                if not destinos:
                    evento.estado = EventoOutbox.Estado.ENVIADO
                    evento.procesado_en = ahora_ref
                    evento.ultimo_error = ""
                    evento.full_clean()
                    evento.save(
                        update_fields=[
                            "estado",
                            "procesado_en",
                            "ultimo_error",
                            "fecha_actualizacion",
                        ]
                    )
                    enviados += 1
                    sin_destino += 1
                    continue

                secretos = _secretos_instancias(destinos)
                try:
                    with transaction.atomic():
                        for instancia in destinos:
                            conector = registry.get_connector(instancia)
                            conector.push_lead(evento)
                except Exception as exc:  # noqa: BLE001 — fallos transitorios o de configuración pasan a backoff/DLQ
                    evento.intentos = int(evento.intentos) + 1
                    evento.ultimo_error = sanitizar_error_outbox(exc, secrets=secretos)
                    if evento.intentos >= evento.max_intentos:
                        evento.estado = EventoOutbox.Estado.DLQ
                        evento.procesado_en = ahora_ref
                        dlq += 1
                    else:
                        evento.estado = EventoOutbox.Estado.FALLIDO
                        espera = calcular_backoff_segundos(evento.intentos)
                        evento.proximo_intento_en = ahora_ref + timedelta(seconds=espera)
                        fallidos += 1
                    evento.full_clean()
                    evento.save(
                        update_fields=[
                            "estado",
                            "intentos",
                            "proximo_intento_en",
                            "procesado_en",
                            "ultimo_error",
                            "fecha_actualizacion",
                        ]
                    )
                    logger.warning(
                        "despachar_lote_outbox fallo | evento=%s | tipo=%s | estado=%s | intentos=%d/%d",
                        evento.id_evento,
                        evento.tipo_evento,
                        evento.estado,
                        evento.intentos,
                        evento.max_intentos,
                    )
                else:
                    evento.estado = EventoOutbox.Estado.ENVIADO
                    evento.procesado_en = ahora_ref
                    evento.ultimo_error = ""
                    evento.full_clean()
                    evento.save(
                        update_fields=[
                            "estado",
                            "procesado_en",
                            "ultimo_error",
                            "fecha_actualizacion",
                        ]
                    )
                    enviados += 1

    return {
        "procesados": enviados + fallidos + dlq,
        "enviados": enviados,
        "sin_destino": sin_destino,
        "fallidos": fallidos,
        "dlq": dlq,
        "omitidos_bloqueo": omitidos_bloqueo,
    }
