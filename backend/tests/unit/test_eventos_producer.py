"""
Backfill de cobertura — apps/eventos/producer.py (plan "Cero Dudas").

Cero llamadas de red: el Producer Kafka se reemplaza por un fake en memoria.
Cubre:
- ``_get_broker_url`` / ``_derive_topic``.
- ``_get_producer``: sin librería, sin broker, conexión OK (singleton) y fallo.
- ``publicar_evento``: degradación a log (False), publicación OK (True, envelope
  correcto) y excepción del producer (False).
- ``_delivery_report`` con y sin error.
"""
import json
from unittest import mock

import pytest

from django.test import override_settings

from apps.eventos import producer

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """El módulo cachea el producer en un global: aislar cada test."""
    monkeypatch.setattr(producer, "_producer_instance", None)
    # El logger del proyecto no propaga a root -> caplog no veria los records.
    monkeypatch.setattr(producer.logger, "propagate", True)


class FakeProducer:
    def __init__(self, config):
        self.config = config
        self.produced = []
        self.polled = 0

    def produce(self, topic, key, value, on_delivery):
        self.produced.append({"topic": topic, "key": key, "value": value})

    def poll(self, timeout):
        self.polled += 1


# ── _get_broker_url / _derive_topic ───────────────────────────────────────────


class TestHelpers:
    def test_broker_url_vacio_por_defecto(self):
        # settings de test no definen KAFKA_BROKER_URL
        assert producer._get_broker_url() == ""

    @override_settings(KAFKA_BROKER_URL="kafka:9092")
    def test_broker_url_desde_settings(self):
        assert producer._get_broker_url() == "kafka:9092"

    def test_derive_topic_por_dominio(self):
        assert producer._derive_topic("ventas.pedido.creado") == "omni.ventas"
        assert producer._derive_topic("inventario.movimiento.registrado") == "omni.inventario"

    def test_derive_topic_evento_vacio(self):
        assert producer._derive_topic("") == "omni.general"

    @override_settings(KAFKA_TOPIC_PREFIX="acme")
    def test_derive_topic_prefijo_custom(self):
        assert producer._derive_topic("finanzas.pago.registrado") == "acme.finanzas"

    def test_settings_rotos_degradan_con_defaults(self):
        """Si django.conf.settings no está disponible, los helpers no explotan."""
        class _SettingsRotos:
            def __getattr__(self, name):
                raise RuntimeError("settings no configurados")

        with mock.patch("django.conf.settings", _SettingsRotos()):
            assert producer._get_broker_url() == ""
            assert producer._derive_topic("ventas.pedido.creado") == "omni.ventas"


# ── _get_producer ─────────────────────────────────────────────────────────────


class TestGetProducer:
    def test_sin_libreria_kafka(self, monkeypatch):
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", False)
        assert producer._get_producer() is None

    def test_sin_broker_configurado(self, monkeypatch):
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        assert producer._get_producer() is None

    @override_settings(KAFKA_BROKER_URL="kafka:9092", KAFKA_PRODUCER_CONFIG={"client.id": "omni"})
    def test_conexion_ok_y_singleton(self, monkeypatch):
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(producer, "Producer", FakeProducer, raising=False)

        p1 = producer._get_producer()
        assert isinstance(p1, FakeProducer)
        assert p1.config["bootstrap.servers"] == "kafka:9092"
        assert p1.config["client.id"] == "omni"
        # Singleton: la segunda llamada reutiliza la instancia
        assert producer._get_producer() is p1

    @override_settings(KAFKA_BROKER_URL="kafka:9092")
    def test_fallo_de_conexion_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(
            producer, "Producer",
            mock.Mock(side_effect=RuntimeError("broker inaccesible")),
            raising=False,
        )
        assert producer._get_producer() is None


# ── publicar_evento ───────────────────────────────────────────────────────────


class TestPublicarEvento:
    def test_degradado_a_log_devuelve_false(self, monkeypatch, caplog):
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", False)
        with caplog.at_level("WARNING", logger="omni.eventos"):
            ok = producer.publicar_evento("ventas.pedido.creado", {"id": "p1"}, empresa_id="e1")
        assert ok is False
        assert any("DEGRADADO" in r.getMessage() for r in caplog.records)

    @override_settings(KAFKA_BROKER_URL="kafka:9092")
    def test_publica_envelope_correcto(self, monkeypatch):
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(producer, "Producer", FakeProducer, raising=False)

        ok = producer.publicar_evento(
            "ventas.pedido.creado", {"numero": "PED-1"}, empresa_id="emp-1"
        )
        assert ok is True

        fake = producer._producer_instance
        assert fake.polled == 1
        assert len(fake.produced) == 1
        msg = fake.produced[0]
        assert msg["topic"] == "omni.ventas"
        assert msg["key"] == "emp-1"  # particionado por empresa

        envelope = json.loads(msg["value"].decode("utf-8"))
        assert envelope["event_type"] == "ventas.pedido.creado"
        assert envelope["empresa_id"] == "emp-1"
        assert envelope["version"] == "1.0"
        assert envelope["payload"] == {"numero": "PED-1"}
        assert envelope["event_id"]  # uuid generado
        assert envelope["timestamp"]

    @override_settings(KAFKA_BROKER_URL="kafka:9092")
    def test_sin_empresa_usa_event_id_como_key(self, monkeypatch):
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(producer, "Producer", FakeProducer, raising=False)

        assert producer.publicar_evento("crm.cliente.creado", {}) is True
        msg = producer._producer_instance.produced[0]
        envelope = json.loads(msg["value"].decode("utf-8"))
        assert msg["key"] == envelope["event_id"]

    @override_settings(KAFKA_BROKER_URL="kafka:9092")
    def test_error_al_producir_devuelve_false(self, monkeypatch, caplog):
        class ProducerRoto(FakeProducer):
            def produce(self, *a, **k):
                raise BufferError("cola llena")

        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(producer, "Producer", ProducerRoto, raising=False)

        with caplog.at_level("WARNING", logger="omni.eventos"):
            ok = producer.publicar_evento("ventas.pedido.creado", {"x": 1})
        assert ok is False
        assert any("error al producir" in r.getMessage() for r in caplog.records)


# ── _delivery_report ──────────────────────────────────────────────────────────


class TestDeliveryReport:
    def test_con_error_loguea_warning(self, caplog):
        msg = mock.Mock()
        msg.topic.return_value = "omni.ventas"
        with caplog.at_level("WARNING", logger="omni.eventos"):
            producer._delivery_report("timeout", msg)
        assert any("fallo al entregar" in r.getMessage() for r in caplog.records)

    def test_sin_error_loguea_debug(self, caplog):
        msg = mock.Mock()
        msg.topic.return_value = "omni.ventas"
        msg.partition.return_value = 0
        msg.offset.return_value = 42
        with caplog.at_level("DEBUG", logger="omni.eventos"):
            producer._delivery_report(None, msg)
        assert any("entregado" in r.getMessage() for r in caplog.records)
