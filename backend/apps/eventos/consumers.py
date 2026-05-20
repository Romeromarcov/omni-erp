"""
OmniEventConsumer — Consume eventos desde Redpanda/Kafka.

Uso:
    python manage.py consumir_eventos --topics omni.ventas omni.inventario

El consumer se ejecuta en un loop bloqueante; para detenerlo usa Ctrl+C.
Si confluent-kafka no está instalado o el broker no está disponible,
el comando termina con un mensaje informativo.
"""
import json
import logging
import signal
import sys

logger = logging.getLogger("omni.eventos.consumer")

try:
    from confluent_kafka import Consumer, KafkaException

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False


# ── Registro de handlers por event_type ───────────────────────────────────────

_handlers: dict[str, list] = {}


def register_handler(event_type: str):
    """
    Decorador para registrar un handler de eventos.

    Uso:
        @register_handler("ventas.pedido.creado")
        def handle_pedido_creado(envelope: dict) -> None:
            ...
    """
    def decorator(fn):
        _handlers.setdefault(event_type, []).append(fn)
        return fn
    return decorator


# ── Handlers por defecto (stubs) ──────────────────────────────────────────────

@register_handler("ventas.pedido.creado")
def _handle_pedido_creado(envelope: dict) -> None:
    logger.info(
        "[ventas.pedido.creado] pedido_id=%s empresa=%s",
        envelope.get("payload", {}).get("pedido_id"),
        envelope.get("empresa_id"),
    )


@register_handler("ventas.pedido.actualizado")
def _handle_pedido_actualizado(envelope: dict) -> None:
    logger.info(
        "[ventas.pedido.actualizado] pedido_id=%s",
        envelope.get("payload", {}).get("pedido_id"),
    )


@register_handler("ventas.factura.creada")
def _handle_factura_creada(envelope: dict) -> None:
    logger.info(
        "[ventas.factura.creada] factura_id=%s numero=%s",
        envelope.get("payload", {}).get("factura_id"),
        envelope.get("payload", {}).get("numero_factura"),
    )


@register_handler("inventario.movimiento.registrado")
def _handle_movimiento(envelope: dict) -> None:
    logger.info(
        "[inventario.movimiento.registrado] movimiento_id=%s tipo=%s",
        envelope.get("payload", {}).get("movimiento_id"),
        envelope.get("payload", {}).get("tipo_movimiento"),
    )


@register_handler("finanzas.pago.registrado")
def _handle_pago(envelope: dict) -> None:
    logger.info(
        "[finanzas.pago.registrado] pago_id=%s monto=%s",
        envelope.get("payload", {}).get("pago_id"),
        envelope.get("payload", {}).get("monto"),
    )


# ── Consumer principal ────────────────────────────────────────────────────────

def _process_message(msg_value: bytes) -> None:
    """Deserializa el envelope y despacha al handler correspondiente."""
    try:
        envelope = json.loads(msg_value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("OmniEventConsumer: mensaje inválido (no JSON): %s", exc)
        return

    event_type = envelope.get("event_type", "")
    handlers = _handlers.get(event_type, [])

    if not handlers:
        logger.debug("OmniEventConsumer: sin handler para '%s'", event_type)
        return

    for handler in handlers:
        try:
            handler(envelope)
        except Exception as exc:
            logger.exception(
                "OmniEventConsumer: handler '%s' lanzó excepción para evento '%s': %s",
                handler.__name__,
                event_type,
                exc,
            )


def run_consumer(
    topics: list[str],
    group_id: str = "omni-erp-consumer",
    poll_timeout: float = 1.0,
) -> None:
    """
    Ejecuta el consumer en un loop bloqueante.

    Args:
        topics: Lista de topics a suscribir.
        group_id: Consumer group ID.
        poll_timeout: Segundos de timeout por ciclo de poll.
    """
    if not KAFKA_AVAILABLE:
        logger.error(
            "OmniEventConsumer: confluent-kafka no está instalado. "
            "Instala con: pip install confluent-kafka"
        )
        return

    try:
        from django.conf import settings

        broker_url = getattr(settings, "KAFKA_BROKER_URL", "") or ""
    except Exception:
        broker_url = ""

    if not broker_url:
        logger.error(
            "OmniEventConsumer: KAFKA_BROKER_URL no está configurado. "
            "Configura la variable de entorno o settings.KAFKA_BROKER_URL."
        )
        return

    consumer_config = {
        "bootstrap.servers": broker_url,
        "group.id": group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    }

    consumer = Consumer(consumer_config)
    consumer.subscribe(topics)
    logger.info(
        "OmniEventConsumer iniciado — broker=%s topics=%s group=%s",
        broker_url,
        topics,
        group_id,
    )

    # Manejo de señal para shutdown limpio
    running = [True]

    def _shutdown(signum, frame):
        logger.info("OmniEventConsumer: señal de cierre recibida, deteniendo...")
        running[0] = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while running[0]:
            msg = consumer.poll(timeout=poll_timeout)
            if msg is None:
                continue
            if msg.error():
                logger.warning("OmniEventConsumer: error de Kafka: %s", msg.error())
                continue
            _process_message(msg.value())
    except KafkaException as exc:
        logger.exception("OmniEventConsumer: KafkaException: %s", exc)
    finally:
        consumer.close()
        logger.info("OmniEventConsumer detenido.")
