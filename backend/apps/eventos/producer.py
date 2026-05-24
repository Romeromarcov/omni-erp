"""
OmniEventProducer — Publica eventos de dominio a Redpanda/Kafka.

Si KAFKA_BROKER_URL no está configurado o el broker no responde,
los eventos se registran en el log con level WARNING (degradación graceful).
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("omni.eventos")

try:
    from confluent_kafka import Producer

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

_producer_instance = None


def _get_broker_url() -> str:
    """Obtiene la URL del broker desde Django settings."""
    try:
        from django.conf import settings

        return getattr(settings, "KAFKA_BROKER_URL", "") or ""
    except Exception:
        return ""


def _get_producer():
    """Retorna una instancia singleton del Producer, o None si no está disponible."""
    global _producer_instance

    if not KAFKA_AVAILABLE:
        return None

    broker_url = _get_broker_url()
    if not broker_url:
        return None

    if _producer_instance is not None:
        return _producer_instance

    try:
        from django.conf import settings

        config = getattr(settings, "KAFKA_PRODUCER_CONFIG", {})
        # Asegurar que bootstrap.servers esté configurado
        config = {**config, "bootstrap.servers": broker_url}
        _producer_instance = Producer(config)
        logger.info("OmniEventProducer conectado a broker: %s", broker_url)
        return _producer_instance
    except Exception as exc:
        logger.warning(
            "OmniEventProducer: no se pudo conectar al broker (%s). "
            "Los eventos se registrarán en el log.",
            exc,
        )
        return None


def _derive_topic(event_type: str) -> str:
    """
    Deriva el topic Kafka desde el tipo de evento.

    Ejemplos:
        "ventas.pedido.creado"          → "omni.ventas"
        "inventario.movimiento.reg..."  → "omni.inventario"
        "finanzas.pago.registrado"      → "omni.finanzas"
    """
    try:
        from django.conf import settings

        prefix = getattr(settings, "KAFKA_TOPIC_PREFIX", "omni")
    except Exception:
        prefix = "omni"

    domain = event_type.split(".")[0] if event_type else "general"
    return f"{prefix}.{domain}"


def _delivery_report(err, msg):
    """Callback de confirmación de entrega."""
    if err is not None:
        logger.warning(
            "OmniEventProducer: fallo al entregar mensaje al topic '%s': %s",
            msg.topic(),
            err,
        )
    else:
        logger.debug(
            "OmniEventProducer: evento entregado a %s [%d] offset %d",
            msg.topic(),
            msg.partition(),
            msg.offset(),
        )


def publicar_evento(
    tipo: str,
    payload: dict[str, Any],
    empresa_id: str | None = None,
) -> bool:
    """
    Publica un evento de dominio.

    Args:
        tipo: e.g. "ventas.pedido.creado", "inventario.movimiento.registrado"
        payload: dict con los datos del evento
        empresa_id: UUID de la empresa (para particionado)

    Returns:
        True si se publicó al broker, False si se degradó a log
    """
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": tipo,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "empresa_id": empresa_id,
        "version": "1.0",
        "payload": payload,
    }

    producer = _get_producer()
    if producer is None:
        logger.warning(
            "OmniEventProducer [DEGRADADO] evento=%s empresa=%s data=%s",
            tipo,
            empresa_id,
            json.dumps(payload, default=str, ensure_ascii=False),
        )
        return False

    topic = _derive_topic(tipo)
    try:
        producer.produce(
            topic=topic,
            key=empresa_id or envelope["event_id"],
            value=json.dumps(envelope, default=str, ensure_ascii=False).encode("utf-8"),
            on_delivery=_delivery_report,
        )
        producer.poll(0)  # trigger callbacks without blocking
        return True
    except Exception as exc:
        logger.warning(
            "OmniEventProducer: error al producir evento '%s': %s. "
            "Evento guardado en log: %s",
            tipo,
            exc,
            json.dumps(envelope, default=str, ensure_ascii=False),
        )
        return False
