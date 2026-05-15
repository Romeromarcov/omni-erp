"""
Omni Event Store — capa de publicación y consumo de eventos.

Usa Redpanda (Kafka-compatible) como broker de eventos.
En entornos sin Kafka (dev local sin Docker), opera en modo stub
controlado por la variable de entorno KAFKA_BOOTSTRAP_SERVERS.

Convención de topics:
  omni.{modulo}.{entidad}.{accion}
  Ejemplos:
    omni.core.empresa.creada
    omni.ventas.pedido.confirmado
    omni.inventario.movimiento.registrado

Estructura canónica de un evento:
{
    "event_id":     "<uuid7>",
    "event_type":   "omni.core.empresa.creada",
    "schema_version": "1.0",
    "occurred_at":  "<ISO8601 UTC>",
    "tenant_id":    "<empresa_id>",
    "actor_id":     "<usuario_id o 'system'>",
    "payload":      { ...campos específicos del evento... },
    "metadata":     { ...contexto adicional opcional... }
}
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("omni.events")

# Bootstrap servers: "redpanda:9092" en Docker, "localhost:19092" en host
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "")

# Topic base
TOPIC_PREFIX = "omni"


def _make_event_id() -> str:
    """Genera un ID único para el evento (UUID4 estándar por ahora; migrar a UUID7 cuando esté disponible)."""
    return str(uuid.uuid4())


def build_event(
    *,
    event_type: str,
    tenant_id: str,
    payload: dict[str, Any],
    actor_id: str = "system",
    schema_version: str = "1.0",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Construye el sobre canónico de un evento Omni.

    Args:
        event_type:      Nombre del evento en formato `omni.modulo.entidad.accion`.
        tenant_id:       ID de la empresa (contexto multi-tenant).
        payload:         Datos específicos del evento.
        actor_id:        Quién originó el evento (usuario o 'system').
        schema_version:  Versión del schema del payload.
        metadata:        Contexto adicional (trace_id, request_id, etc.).

    Returns:
        Diccionario con el sobre canónico completo.
    """
    return {
        "event_id": _make_event_id(),
        "event_type": event_type,
        "schema_version": schema_version,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "payload": payload,
        "metadata": metadata or {},
    }


def _get_producer():
    """
    Devuelve un Producer de Kafka/Redpanda o None si no hay broker configurado.
    El Producer se crea lazy para no bloquear el arranque de Django.
    """
    if not KAFKA_BOOTSTRAP_SERVERS:
        return None
    try:
        from confluent_kafka import Producer  # type: ignore[import-untyped]

        return Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
    except ImportError:
        logger.warning("confluent-kafka no instalado; eventos en modo stub")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo conectar a Kafka (%s); eventos en modo stub", exc)
        return None


def publish(
    *,
    event_type: str,
    tenant_id: str,
    payload: dict[str, Any],
    actor_id: str = "system",
    schema_version: str = "1.0",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Publica un evento en Redpanda/Kafka.

    Si no hay broker disponible (KAFKA_BOOTSTRAP_SERVERS vacío o conexión fallida),
    el evento se loguea como WARNING y se retorna el sobre sin publicar.
    Esto garantiza que el código de negocio nunca falle por el event store.

    Returns:
        El sobre del evento publicado (útil para logging y tests).
    """
    event = build_event(
        event_type=event_type,
        tenant_id=tenant_id,
        payload=payload,
        actor_id=actor_id,
        schema_version=schema_version,
        metadata=metadata,
    )

    # El topic se deriva del tipo de evento: omni.core.empresa.creada → omni.core.empresa.creada
    topic = event_type

    producer = _get_producer()
    if producer is None:
        logger.debug(
            "EVENT stub (sin broker): %s | tenant=%s | event_id=%s",
            event_type,
            tenant_id,
            event["event_id"],
        )
        return event

    try:
        producer.produce(
            topic=topic,
            key=tenant_id.encode("utf-8"),
            value=json.dumps(event).encode("utf-8"),
            headers={"event-type": event_type, "schema-version": schema_version},
        )
        producer.flush(timeout=5)
        logger.info(
            "EVENT published: %s | tenant=%s | event_id=%s",
            event_type,
            tenant_id,
            event["event_id"],
        )
    except Exception as exc:  # noqa: BLE001
        # El event store nunca debe romper la transacción de negocio
        logger.error(
            "EVENT publish failed: %s | error=%s | event_id=%s",
            event_type,
            exc,
            event["event_id"],
        )

    return event


# ── Constantes de tipos de evento por módulo ─────────────────────────────────
# Centralizar los nombres evita typos y facilita búsqueda.

class CoreEvents:
    EMPRESA_CREADA = "omni.core.empresa.creada"
    EMPRESA_ACTUALIZADA = "omni.core.empresa.actualizada"
    USUARIO_CREADO = "omni.core.usuario.creado"
    ROL_ASIGNADO = "omni.core.usuario.rol_asignado"


class VentasEvents:
    PEDIDO_CREADO = "omni.ventas.pedido.creado"
    PEDIDO_CONFIRMADO = "omni.ventas.pedido.confirmado"
    PEDIDO_CANCELADO = "omni.ventas.pedido.cancelado"
    FACTURA_EMITIDA = "omni.ventas.factura.emitida"
    PAGO_REGISTRADO = "omni.ventas.pago.registrado"


class InventarioEvents:
    MOVIMIENTO_REGISTRADO = "omni.inventario.movimiento.registrado"
    STOCK_BAJO = "omni.inventario.stock.bajo"
    AJUSTE_REALIZADO = "omni.inventario.ajuste.realizado"


class CobranzaEvents:
    CXC_VENCIDA = "omni.cobranza.cxc.vencida"
    GESTION_REGISTRADA = "omni.cobranza.gestion.registrada"
    PAGO_PARCIAL = "omni.cobranza.pago.parcial"
    PAGO_TOTAL = "omni.cobranza.pago.total"
