"""
Tests de integración y seguridad para OpenTelemetry opt-in (Plan 05 · P2-6).

Cubre:
  1. Comportamiento 100 % no-op cuando ``OTEL_ENABLED=false`` (o ausente):
     ``init_telemetry``, ``wsgi``/``asgi``/``celery`` signals, ``trazar_operacion``,
     ``inject_trace_headers``, ``extract_trace_context``, ``OTelTraceLogFilter``
     (``trace_id="-"``), ``apps.eventos.producer`` y ``consumers`` sin mutar esquema.
  2. Flujo end-to-end con ``OTEL_ENABLED=true`` + ``InMemorySpanExporter``:
     petición HTTP Django (``Client().get``) → tarea Celery → ``publicar_evento``
     (Kafka headers) → ``consumers._process_message``: verifica mismo ``trace_id``,
     jerarquía parent-child exacta (``parent.span_id``) y correlación de logs en
     ``OTelTraceLogFilter`` (``trace_id`` 32 hex, ``span_id`` 16 hex).
  3. Propagación W3C TraceContext tolerante a ``bytes``/``str``, formatos Kafka,
     ``None``, ``\\x00``, UTF-8 inválido y cabeceras malformadas sin excepciones.
  4. Sanitización R-CODE-8 en ``trazar_operacion`` y degradación fail-safe cuando
     falta ``OTEL_EXPORTER_OTLP_ENDPOINT`` o falla el exportador/instrumentador.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
from unittest import mock

from celery import shared_task
from celery.signals import worker_process_init, worker_process_shutdown
from django.http import JsonResponse
from django.test import Client, override_settings
from django.urls import clear_url_caches, path
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest

from apps.core import telemetry
from apps.core.telemetry import (
    OTelTraceLogFilter,
    extract_trace_context,
    init_telemetry,
    inject_trace_headers,
    is_telemetry_active,
    is_telemetry_enabled,
    reset_telemetry_for_tests,
    shutdown_telemetry,
    trazar_operacion,
)
from apps.eventos import consumers, producer

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CAPTURED_E2E_LOGS: list[tuple[str, str, str]] = []


@shared_task(name="tests.p26_otel_e2e_task")
def _p26_otel_e2e_task(empresa_id: str) -> bool:
    """Tarea Celery de prueba que emite log correlacionado y publica un evento Kafka."""
    apps_logger = logging.getLogger("apps")
    apps_logger.info("Ejecutando tarea Celery trazada para empresa %s", empresa_id)
    return producer.publicar_evento(
        tipo="otel.e2e.pedido_trazado",
        payload={"pedido_id": 701},
        empresa_id=empresa_id,
    )


def _e2e_http_view(request):
    """Vista Django mínima para validar traza HTTP → Celery → Evento."""
    res = _p26_otel_e2e_task.delay(empresa_id="emp-otel-1")
    return JsonResponse({"ok": bool(res.get())})


urlpatterns = [
    path("_test/otel-e2e/", _e2e_http_view, name="p26_otel_e2e"),
]


class _FakeKafkaProducer:
    def __init__(self, config: dict):
        self.config = config
        self.produced: list[dict] = []
        self.polled = 0

    def produce(self, topic, key, value, on_delivery, headers=None):
        self.produced.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
                "headers": headers,
            }
        )

    def poll(self, timeout):
        self.polled += 1


class _LegacyFakeProducerNoHeaders:
    """Simula un fake legado que NO acepta kwarg ``headers`` cuando OTel está apagado."""

    def __init__(self, config: dict):
        self.produced: list[dict] = []

    def produce(self, topic, key, value, on_delivery):
        self.produced.append({"topic": topic, "key": key, "value": value})

    def poll(self, timeout):
        return None


@pytest.fixture(autouse=True)
def _clean_otel_and_eventos(monkeypatch):
    """Aísla estado global de OpenTelemetry, productores y URLconf en cada test."""
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_ENVIRONMENT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setattr(producer, "_producer_instance", None)
    _CAPTURED_E2E_LOGS.clear()
    reset_telemetry_for_tests()
    clear_url_caches()
    yield
    monkeypatch.setattr(producer, "_producer_instance", None)
    _CAPTURED_E2E_LOGS.clear()
    reset_telemetry_for_tests()
    clear_url_caches()


# ── 1. No-op puro cuando OTEL_ENABLED=false ──────────────────────────────────


class TestOtelDesactivadoNoOp:
    @pytest.mark.parametrize("raw_val", [None, "", "false", "0", "no", "off", "FALSE"])
    def test_init_telemetry_es_noop_puro(self, monkeypatch, raw_val):
        if raw_val is None:
            monkeypatch.delenv("OTEL_ENABLED", raising=False)
        else:
            monkeypatch.setenv("OTEL_ENABLED", raw_val)

        assert is_telemetry_enabled() is False

        with (
            mock.patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as bsp_mock,
            mock.patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as exp_mock,
        ):
            assert init_telemetry(service_name="omni-erp-test") is False
            bsp_mock.assert_not_called()
            exp_mock.assert_not_called()

        assert is_telemetry_active() is False

        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        assert DjangoInstrumentor().is_instrumented_by_opentelemetry is False
        assert CeleryInstrumentor().is_instrumented_by_opentelemetry is False
        assert RequestsInstrumentor().is_instrumented_by_opentelemetry is False

    def test_helpers_y_filter_logging_son_noop_sin_otel(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")

        with trazar_operacion("op.noop", empresa_id="emp-1") as span:
            assert span is None

        @trazar_operacion("op.decorada.noop")
        def _sumar(a: int, b: int) -> int:
            return a + b

        assert _sumar(2, 3) == 5

        assert inject_trace_headers() == {}
        assert inject_trace_headers({"x-custom": "ok"}) == {"x-custom": "ok"}
        assert (
            extract_trace_context({"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}) is None
        )

        log_filter = OTelTraceLogFilter()
        record = logging.LogRecord("apps", logging.INFO, __file__, 1, "mensaje %s", ("seguro",), None)
        assert log_filter.filter(record) is True
        assert record.trace_id == "-"
        assert record.span_id == "-"

        # Verifica que el filtro conectado en settings.LOGGING["handlers"]["console"] inyecta "-"
        console_handler = next(h for h in logging.getLogger("apps").handlers if h.name == "console")
        rec_console = logging.LogRecord("apps", logging.INFO, __file__, 2, "hola", (), None)
        for flt in console_handler.filters:
            flt.filter(rec_console)
        assert rec_console.trace_id == "-"
        assert rec_console.span_id == "-"

    @override_settings(KAFKA_BROKER_URL="kafka:9092")
    def test_entrypoints_y_eventos_sin_impacto_cuando_desactivado(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(producer, "Producer", _LegacyFakeProducerNoHeaders, raising=False)

        # wsgi / asgi reload no activan instrumentación cuando OTEL_ENABLED=false
        import config.asgi as asgi_mod
        import config.wsgi as wsgi_mod

        importlib.reload(wsgi_mod)
        importlib.reload(asgi_mod)
        assert is_telemetry_active() is False

        # Señales Celery tampoco activan tracing
        worker_process_init.send(sender=None)
        worker_process_shutdown.send(sender=None)
        assert is_telemetry_active() is False

        # producer.publicar_evento no pasa kwarg headers ni altera el esquema
        ok = producer.publicar_evento("ventas.pedido.creado", {"pedido_id": 1}, empresa_id="emp-1")
        assert ok is True
        msg = producer._producer_instance.produced[0]
        envelope = json.loads(msg["value"].decode("utf-8"))
        assert set(envelope.keys()) == {"event_id", "event_type", "timestamp", "empresa_id", "version", "payload"}

        # consumers._process_message funciona igual sin contexto
        seen: list[str] = []
        consumers._handlers.setdefault("otel.noop.test", []).append(lambda env: seen.append(env["event_type"]))
        try:
            consumers._process_message(json.dumps({"event_type": "otel.noop.test"}).encode("utf-8"))
        finally:
            consumers._handlers["otel.noop.test"].clear()
        assert seen == ["otel.noop.test"]


# ── 2. End-to-End con OTEL_ENABLED=true + InMemorySpanExporter ───────────────


class _SpyLogHandler(logging.Handler):
    """Captura trace_id/span_id ya inyectados por OTelTraceLogFilter en handlers reales."""

    def emit(self, record: logging.LogRecord) -> None:
        _CAPTURED_E2E_LOGS.append(
            (
                record.getMessage(),
                getattr(record, "trace_id", ""),
                getattr(record, "span_id", ""),
            )
        )


class TestOtelEndToEnd:
    @override_settings(ROOT_URLCONF=__name__, KAFKA_BROKER_URL="kafka:9092")
    def test_flujo_http_celery_kafka_consumer_mismo_trace_id(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setenv("OTEL_SERVICE_NAME", "omni-erp-e2e")
        monkeypatch.setenv("OTEL_ENVIRONMENT", "staging-e2e")
        monkeypatch.setattr(producer, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(producer, "Producer", _FakeKafkaProducer, raising=False)

        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True
        # Idempotente en segunda llamada
        assert init_telemetry() is True
        assert is_telemetry_active() is True

        apps_logger = logging.getLogger("apps")
        eventos_logger = logging.getLogger("omni.eventos")
        spy_handler = _SpyLogHandler()
        spy_handler.addFilter(OTelTraceLogFilter())
        apps_logger.addHandler(spy_handler)
        eventos_logger.addHandler(spy_handler)

        consumed_envelopes: list[dict] = []

        def _handler_e2e(envelope: dict) -> None:
            consumed_envelopes.append(envelope)
            eventos_logger.info("Consumido evento %s", envelope.get("event_id"))

        consumers._handlers.setdefault("otel.e2e.pedido_trazado", []).append(_handler_e2e)
        try:
            http_client = Client()
            response = http_client.get("/_test/otel-e2e/")
            assert response.status_code == 200
            assert response.json() == {"ok": True}

            fake_prod = producer._producer_instance
            assert fake_prod is not None
            assert len(fake_prod.produced) == 1
            produced_msg = fake_prod.produced[0]
            assert "traceparent" in produced_msg["headers"]
            assert produced_msg["headers"]["traceparent"].startswith("00-")

            # Simula consumo en otro proceso pasando cabeceras estilo librdkafka (bytes)
            kafka_headers = [(k, v.encode("utf-8")) for k, v in produced_msg["headers"].items()]
            consumers._process_message(produced_msg["value"], headers=kafka_headers)
        finally:
            consumers._handlers["otel.e2e.pedido_trazado"].clear()
            apps_logger.removeHandler(spy_handler)
            eventos_logger.removeHandler(spy_handler)

        assert len(consumed_envelopes) == 1
        assert consumed_envelopes[0]["payload"] == {"pedido_id": 701}

        spans = exporter.get_finished_spans()
        by_name = {s.name: s for s in spans}

        http_span = next(s for s in spans if s.name.startswith("GET "))
        celery_span = by_name["run/tests.p26_otel_e2e_task"]
        pub_span = by_name["eventos.publicar"]
        con_span = by_name["eventos.consumir"]

        # Mismo trace_id en toda la cadena end-to-end
        trace_ids = {s.context.trace_id for s in (http_span, celery_span, pub_span, con_span)}
        assert len(trace_ids) == 1
        trace_id_int = next(iter(trace_ids))
        assert trace_id_int != 0

        # Cadena exacta parent -> child
        assert http_span.parent is None
        assert celery_span.parent is not None
        assert celery_span.parent.span_id == http_span.context.span_id
        assert pub_span.parent is not None
        assert pub_span.parent.span_id == celery_span.context.span_id
        assert con_span.parent is not None
        assert con_span.parent.span_id == pub_span.context.span_id

        # Resource metadata
        assert http_span.resource.attributes["service.name"] == "omni-erp-e2e"
        assert http_span.resource.attributes["deployment.environment"] == "staging-e2e"

        # Logs correlacionados con hex de 32 y 16 caracteres
        expected_trace_hex = f"{trace_id_int:032x}"
        celery_logs = [entry for entry in _CAPTURED_E2E_LOGS if "Ejecutando tarea Celery" in entry[0]]
        consumer_logs = [entry for entry in _CAPTURED_E2E_LOGS if "Consumido evento" in entry[0]]
        assert celery_logs and celery_logs[0][1] == expected_trace_hex
        assert celery_logs[0][2] == f"{celery_span.context.span_id:016x}"
        assert consumer_logs and consumer_logs[0][1] == expected_trace_hex
        assert consumer_logs[0][2] == f"{con_span.context.span_id:016x}"

        # Filtro oficial de Django LOGGING["handlers"]["console"] también tiene hex válidos
        console_handler = next(h for h in logging.getLogger("apps").handlers if h.name == "console")
        assert any(isinstance(f, OTelTraceLogFilter) for f in console_handler.filters)

    def test_decorador_sync_async_y_error_seguro(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True

        @trazar_operacion("op.sync", modulo="ventas")
        def _op_sync(x: int) -> int:
            return x * 2

        @trazar_operacion("op.async", modulo="agentes")
        async def _op_async(x: int) -> int:
            return x + 1

        assert _op_sync(4) == 8
        assert asyncio.run(_op_async(9)) == 10

        with pytest.raises(ValueError, match="token=valor-omitido"):
            with trazar_operacion("op.error", context="checkout"):
                raise ValueError("Fallo con token=valor-omitido")

        spans = {s.name: s for s in exporter.get_finished_spans()}
        assert spans["op.sync"].attributes["modulo"] == "ventas"
        assert spans["op.async"].attributes["modulo"] == "agentes"
        err_span = spans["op.error"]
        assert err_span.attributes["context"] == "checkout"
        assert err_span.attributes["error.type"] == "ValueError"
        # R-CODE-8: no se exporta el mensaje crudo ni stacktrace de la excepción
        assert err_span.status.description == "ValueError"
        assert not err_span.events

    @override_settings(KAFKA_BROKER_URL="kafka:9092")
    def test_run_consumer_propaga_headers_desde_kafka(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True

        with trazar_operacion("eventos.emitir.externo") as root_span:
            headers = inject_trace_headers()
            expected_trace_id = root_span.get_span_context().trace_id

        msg_mock = mock.Mock()
        msg_mock.error.return_value = None
        msg_mock.value.return_value = json.dumps({"event_type": "otel.run_consumer", "empresa_id": None}).encode(
            "utf-8"
        )
        msg_mock.headers.return_value = [("traceparent", headers["traceparent"].encode("utf-8"))]

        class _FakeKafkaConsumer:
            def __init__(self, _cfg):
                self._calls = 0
                self.closed = False

            def subscribe(self, _topics):
                return None

            def poll(self, timeout=1.0):
                self._calls += 1
                if self._calls == 1:
                    return msg_mock
                raise consumers.KafkaException("fin de prueba")

            def close(self):
                self.closed = True

        seen: list[str] = []
        consumers._handlers.setdefault("otel.run_consumer", []).append(lambda env: seen.append(env["event_type"]))
        monkeypatch.setattr(consumers, "KAFKA_AVAILABLE", True)
        monkeypatch.setattr(consumers, "Consumer", _FakeKafkaConsumer, raising=False)
        monkeypatch.setattr(consumers.signal, "signal", lambda *a, **k: None)

        try:
            consumers.run_consumer(["omni.test"])
        finally:
            consumers._handlers["otel.run_consumer"].clear()

        assert seen == ["otel.run_consumer"]
        con_span = next(s for s in exporter.get_finished_spans() if s.name == "eventos.consumir")
        assert con_span.context.trace_id == expected_trace_id


# ── 3. Propagación W3C TraceContext y resiliencia ante cabeceras corruptas ───


class TestW3CTraceContextPropagation:
    def test_inject_y_extract_soportan_dict_bytes_case_insensitive_y_kafka(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True

        with trazar_operacion("w3c.origen") as span:
            span_ctx = span.get_span_context()
            trace_id = span_ctx.trace_id
            span_id = span_ctx.span_id
            trace_flags = span_ctx.trace_flags
            injected = inject_trace_headers({b"x-app": b"omni", "bad\x00key": "x", "x-nul": "a\x00b"})

        assert injected["x-app"] == "omni"
        assert "bad\x00key" not in injected
        assert "x-nul" not in injected
        assert injected["traceparent"] == f"00-{trace_id:032x}-{span_id:016x}-{trace_flags:02x}"

        # Formato dict str, bytes, mixed case y lista de tuplas Kafka
        for carrier in (
            {"traceparent": injected["traceparent"]},
            {b"TraceParent": injected["traceparent"].encode("utf-8"), b"TraceState": b"rojo=1"},
            [("other", None), ("traceparent", injected["traceparent"].encode("utf-8"))],
        ):
            ctx = extract_trace_context(carrier)
            assert ctx is not None
            with trazar_operacion("w3c.destino", context=ctx) as child:
                assert child.get_span_context().trace_id == trace_id

    @pytest.mark.parametrize(
        "bad_headers",
        [
            None,
            {},
            [],
            "not-a-carrier",
            12345,
            [("traceparent", None)],
            ["tupla-invalida", ("traceparent", 999)],
            {"traceparent": "malformado"},
            {"traceparent": "00-00000000000000000000000000000000-1111111111111111-01"},
            {"traceparent": "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"},
            {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01\x00"},
            {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01\r\nX-Inj: 1"},
            {"traceparent": b"\xff\xfe\xfd"},
            {"traceparent": "00-" + "a" * 600},
        ],
    )
    def test_extract_tolera_cabeceras_corruptas_sin_excepciones(self, monkeypatch, bad_headers):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True

        assert extract_trace_context(bad_headers) is None


# ── 4. Sanitización R-CODE-8 y tolerancia fail-safe ──────────────────────────


class TestSanitizacionYFailSafe:
    def test_trazar_operacion_filtra_llaves_sensibles_y_valores_riesgosos(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True

        with trazar_operacion(
            "seguridad.sanitizacion",
            empresa_id="emp-1",
            cantidad=3,
            activo=True,
            etiquetas=["a", "b"],
            token="valor-omitido",
            access_token="valor-omitido",
            refresh_token="valor-omitido",
            secret="valor-omitido",
            client_secret="valor-omitido",
            password="valor-omitido",
            db_password="valor-omitido",
            api_key="valor-omitido",
            X_Api_Key="valor-omitido",
            authorization="valor-omitido",
            cookie="valor-omitido",
            credential="valor-omitido",
            private_key="valor-omitido",
            detalle_auth="Bearer valor-omitido-largo",
            url_externa="https://usuario:clave@servicio.local/api",
            nulo=None,
        ):
            pass

        span = exporter.get_finished_spans()[0]
        attrs = dict(span.attributes)
        assert attrs["empresa_id"] == "emp-1"
        assert attrs["cantidad"] == 3
        assert attrs["activo"] is True
        assert attrs["etiquetas"] == ("a", "b")
        assert attrs["detalle_auth"] == "[REDACTED]"
        assert attrs["url_externa"] == "[REDACTED]"

        for forbidden in (
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "client_secret",
            "password",
            "db_password",
            "api_key",
            "X_Api_Key",
            "authorization",
            "cookie",
            "credential",
            "private_key",
            "nulo",
        ):
            assert forbidden not in attrs

    @pytest.mark.parametrize("endpoint_val", ["", "not-a-url", "ftp://collector:4318", "http://bad host:4318"])
    def test_failsafe_endpoint_ausente_o_invalido_genera_spans_locales(self, monkeypatch, caplog, endpoint_val):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        if endpoint_val:
            monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint_val)

        with (
            caplog.at_level("WARNING", logger="omni.telemetry"),
            mock.patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as bsp_mock,
        ):
            assert init_telemetry() is True
            bsp_mock.assert_not_called()

        assert is_telemetry_active() is True
        assert any("sin exportación" in r.getMessage() for r in caplog.records)

        with trazar_operacion("local.sin_exporter") as span:
            ctx = span.get_span_context()
            assert ctx.is_valid
            assert ctx.trace_id != 0

    def test_failsafe_cuando_falla_exportador_otlp_sin_filtrar_secretos(self, monkeypatch, caplog):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.example.com:4318")

        secreto_simulado = "credencial-otlp-no-filtrar"

        with (
            caplog.at_level("WARNING", logger="omni.telemetry"),
            mock.patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
                side_effect=RuntimeError(f"Header inválido authorization={secreto_simulado}"),
            ),
        ):
            assert init_telemetry() is True

        assert is_telemetry_active() is True
        mensajes = " ".join(r.getMessage() for r in caplog.records)
        assert "RuntimeError" in mensajes
        assert secreto_simulado not in mensajes

        with trazar_operacion("local.post_fallo_exporter") as span:
            assert span.get_span_context().is_valid

    def test_otlp_exporter_valido_configura_batch_processor_y_shutdown(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.example.com:4318")

        exporter_stub = mock.Mock()
        exporter_stub.shutdown.return_value = None
        exporter_stub.force_flush.return_value = True

        with mock.patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
            return_value=exporter_stub,
        ) as exp_cls:
            assert init_telemetry() is True
            exp_cls.assert_called_once()

        shutdown_telemetry()
        exporter_stub.shutdown.assert_called_once()

    def test_consumers_maneja_json_no_dict_y_excepcion_en_handler(self, monkeypatch, caplog):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setattr(logging.getLogger("omni.eventos"), "propagate", True)
        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True

        # JSON válido pero no es dict (lista)
        with caplog.at_level("WARNING", logger="omni.eventos.consumer"):
            consumers._process_message(b"[1, 2, 3]")
        assert any("no es objeto JSON" in r.getMessage() for r in caplog.records)

        # Handler que lanza excepción no detiene el consumidor
        def _handler_roto(_env: dict) -> None:
            raise RuntimeError("fallo de handler simulado")

        consumers._handlers.setdefault("otel.handler.roto", []).append(_handler_roto)
        try:
            with caplog.at_level("ERROR", logger="omni.eventos.consumer"):
                consumers._process_message(
                    json.dumps({"event_type": "otel.handler.roto", "empresa_id": None}).encode("utf-8")
                )
        finally:
            consumers._handlers["otel.handler.roto"].clear()
        assert any("lanzó excepción" in r.getMessage() for r in caplog.records)

    def test_failsafe_cuando_falla_instrumentor_y_signals_celery(self, monkeypatch, caplog):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        exporter = InMemorySpanExporter()

        with (
            caplog.at_level("WARNING", logger="omni.telemetry"),
            mock.patch(
                "opentelemetry.instrumentation.requests.RequestsInstrumentor.instrument",
                side_effect=RuntimeError("fallo simulado"),
            ),
        ):
            assert init_telemetry(span_exporter=exporter) is True

        assert "requests" not in telemetry._INSTRUMENTED
        assert "django" in telemetry._INSTRUMENTED
        assert "celery" in telemetry._INSTRUMENTED
        assert any("requests" in r.getMessage() for r in caplog.records)

        # Señales Celery worker_process_init / worker_process_shutdown operan sin error
        reset_telemetry_for_tests()
        worker_process_init.send(sender=None)
        assert is_telemetry_active() is True
        worker_process_shutdown.send(sender=None)

        # Y si ocurre un fallo dentro del handler de Celery, no bloquea el arranque
        with mock.patch("apps.core.telemetry.init_telemetry", side_effect=RuntimeError("boom")):
            worker_process_init.send(sender=None)

        # Shutdown directo cuando no hay provider es no-op limpio
        reset_telemetry_for_tests()
        shutdown_telemetry()
        assert is_telemetry_active() is False

    def test_override_settings_otel_enabled_y_sanitize_edge_cases(self, monkeypatch):
        from opentelemetry.trace import SpanKind

        monkeypatch.delenv("OTEL_ENABLED", raising=False)
        with override_settings(OTEL_ENABLED=True):
            assert is_telemetry_enabled() is True
        with override_settings(OTEL_ENABLED="yes"):
            assert is_telemetry_enabled() is True

        monkeypatch.setenv("OTEL_ENABLED", "true")
        exporter = InMemorySpanExporter()
        assert init_telemetry(span_exporter=exporter) is True

        # Re-instrumentación explícita es idempotente
        telemetry._INSTRUMENTED.discard("django")
        telemetry._instrument_libraries(telemetry._ACTIVE_PROVIDER)
        assert "django" in telemetry._INSTRUMENTED

        with trazar_operacion("op.spankind", span_kind=SpanKind.CLIENT) as span:
            assert span.kind == SpanKind.CLIENT

        # URL inválida con corchetes IPv6 dispara ValueError en urlsplit
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://[malformed")
        assert telemetry._resolve_valid_otlp_endpoint() is None

        # Span exporter inválido captura excepción sin propagar
        reset_telemetry_for_tests()
        with mock.patch("opentelemetry.sdk.trace.export.SimpleSpanProcessor", side_effect=RuntimeError("bad proc")):
            assert init_telemetry(span_exporter=object()) is True

        # Shutdown tolera fallo del provider
        with mock.patch.object(telemetry._ACTIVE_PROVIDER, "shutdown", side_effect=RuntimeError("shutdown fail")):
            shutdown_telemetry()

        # __exit__ sin __enter__ es no-op seguro
        assert trazar_operacion("sin.enter").__exit__(None, None, None) is False

        # Iterable que falla al iterar en extract_trace_context no propaga excepción
        def _iter_roto():
            raise RuntimeError("iterable roto")
            yield ("traceparent", "x")  # pragma: no cover

        assert extract_trace_context(_iter_roto()) is None

        # reset_telemetry_for_tests tolera fallo al desinstrumentar
        with mock.patch(
            "opentelemetry.instrumentation.django.DjangoInstrumentor.uninstrument",
            side_effect=RuntimeError("uninst fail"),
        ):
            reset_telemetry_for_tests()

        # wsgi entrypoint con OTEL_ENABLED=true en modo local sin exporter inicializa sin error
        import config.wsgi as wsgi_mod

        importlib.reload(wsgi_mod)
        assert is_telemetry_active() is True
        reset_telemetry_for_tests()

        sanitized = telemetry.sanitize_span_attributes(
            {
                123: "ignorar",  # type: ignore[dict-item]
                "": "vacio",
                "   ": "espacios",
                "---": "guiones",
                "mysecretvalue": "valor-omitido",
                "texto_largo": "x" * 700,
                "bytes_ok": b"valor-bytes",
                "traza_error": 'Traceback (most recent call last):\n  File "x.py", line 10',
                "lista_mixta": ["ok", None, "password=no-exponer"],
                "vacio_str": "   \x00  ",
            }
        )
        assert len(sanitized["texto_largo"]) == 512
        assert sanitized["bytes_ok"] == "valor-bytes"
        assert sanitized["traza_error"] == "[REDACTED]"
        assert sanitized["lista_mixta"] == ("ok", "[REDACTED]")
        assert "vacio_str" not in sanitized
        assert "" not in sanitized
        assert "   " not in sanitized
        assert "---" not in sanitized
        assert "mysecretvalue" not in sanitized
        assert 123 not in sanitized
