"""
Tracing distribuido opt-in con OpenTelemetry para Omni ERP (Plan 05 · P2-6).

Diseño 100 % opt-in y fail-safe:
- Solo se activa cuando ``OTEL_ENABLED`` ∈ ``{"1", "true", "yes", "on"}`` (default ``false``).
- Con ``OTEL_ENABLED`` desactivado, ``init_telemetry()`` es un no-op puro: no instancia
  ``BatchSpanProcessor``, no abre sockets ni modifica loggers/handlers globales.
- Cuando está activo, configura ``TracerProvider`` con ``Resource`` (``service.name`` y
  ``deployment.environment``), instrumenta idempotentemente Django, Celery y Requests,
  propaga contexto W3C TraceContext (``traceparent``/``tracestate``), inyecta
  ``trace_id``/``span_id`` en logs vía ``OTelTraceLogFilter`` y sanea atributos sensibles
  conforme a R-CODE-8.
"""

from __future__ import annotations

import functools
import importlib
import inspect
import logging
import os
import re
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import AbstractContextManager, ContextDecorator, nullcontext
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger("omni.telemetry")

_TRUTHY_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_LOCK = threading.RLock()
_INITIALIZED: bool = False
_ACTIVE_PROVIDER: Any = None
_INSTRUMENTED: set[str] = set()

_INSTRUMENTOR_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("django", "opentelemetry.instrumentation.django", "DjangoInstrumentor"),
    ("celery", "opentelemetry.instrumentation.celery", "CeleryInstrumentor"),
    ("requests", "opentelemetry.instrumentation.requests", "RequestsInstrumentor"),
)

_SENSITIVE_KEY_TOKENS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "auth_token",
        "id_token",
        "bearer_token",
        "capability_token",
        "csrf_token",
        "secret",
        "secret_key",
        "client_secret",
        "signing_secret",
        "webhook_secret",
        "password",
        "passwd",
        "pwd",
        "contrasena",
        "clave",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "encryption_key",
        "session_key",
        "signing_key",
        "authorization",
        "auth_header",
        "cookie",
        "set_cookie",
        "credential",
        "credentials",
        "jwt",
        "bearer",
        "dsn",
        "fernet",
        "fernet_key",
    }
)

_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "access_key",
    "encryption_key",
    "session_key",
    "signing_key",
    "cookie",
    "fernet",
)

_UNSAFE_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{6,}", re.IGNORECASE),
    re.compile(r"\b(?:password|passwd|secret|api_key|access_token|token)\s*=", re.IGNORECASE),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE),
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r'\bFile "[^"\n]+", line \d+'),
)

_MAX_ATTR_STR_LEN = 512
_MAX_HEADER_KEY_LEN = 128
_MAX_HEADER_VAL_LEN = 512


def is_telemetry_enabled() -> bool:
    """Indica si el tracing OpenTelemetry está habilitado por configuración."""
    raw = os.environ.get("OTEL_ENABLED")
    if raw is not None:
        return raw.strip().lower() in _TRUTHY_VALUES

    try:
        from django.conf import settings

        if settings.configured:
            val = getattr(settings, "OTEL_ENABLED", False)
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in _TRUTHY_VALUES
    except Exception:  # pragma: no cover - settings corrupto en arranque
        return False
    return False


def is_telemetry_active() -> bool:
    """Indica si existe un TracerProvider inicializado por este módulo."""
    return _INITIALIZED and _ACTIVE_PROVIDER is not None


def _is_sensitive_attr_key(key: str) -> bool:
    """Detecta nombres de atributos que representan credenciales, tokens o secretos (R-CODE-8)."""
    normalized = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
    if not normalized:
        return True
    if normalized in _SENSITIVE_KEY_TOKENS:
        return True
    parts = set(normalized.split("_"))
    if parts & _SENSITIVE_KEY_TOKENS:
        return True
    return any(sub in normalized for sub in _SENSITIVE_SUBSTRINGS)


def _sanitize_scalar_value(value: Any) -> str | bool | int | float | None:
    """Normaliza y sanea un valor escalar para atributo de span."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (bytes, bytearray)):
        text = bytes(value).decode("utf-8", errors="replace")
    else:
        text = str(value)

    text = text.replace("\x00", "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return None
    if any(pattern.search(text) for pattern in _UNSAFE_VALUE_PATTERNS):
        return "[REDACTED]"
    if len(text) > _MAX_ATTR_STR_LEN:
        return text[:_MAX_ATTR_STR_LEN]
    return text


def sanitize_span_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    """Filtra llaves sensibles y sanea valores para atributos OpenTelemetry (R-CODE-8)."""
    if not attributes:
        return {}
    cleaned: dict[str, Any] = {}
    for raw_key, raw_val in attributes.items():
        if not isinstance(raw_key, str):
            continue
        key = raw_key.replace("\x00", "").strip()
        if not key or _is_sensitive_attr_key(key):
            continue
        if isinstance(raw_val, Sequence) and not isinstance(raw_val, (str, bytes, bytearray)):
            items: list[str | bool | int | float] = []
            for item in raw_val:
                scalar = _sanitize_scalar_value(item)
                if scalar is not None:
                    items.append(scalar)
            if items:
                cleaned[key] = tuple(items)
            continue
        scalar = _sanitize_scalar_value(raw_val)
        if scalar is not None:
            cleaned[key] = scalar
    return cleaned


def _resolve_valid_otlp_endpoint() -> str | None:
    """Valida que exista un endpoint OTLP HTTP/HTTPS sintácticamente válido sin exponer credenciales."""
    raw = (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or ""
    ).strip()
    if not raw or "\x00" in raw or any(ch.isspace() for ch in raw):
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return raw


def _load_instrumentor(module_path: str, class_name: str) -> Any:
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


def _instrument_libraries(tracer_provider: Any) -> None:
    """Instrumenta Django, Celery y Requests de forma idempotente y tolerante a fallos."""
    for name, module_path, class_name in _INSTRUMENTOR_TARGETS:
        if name in _INSTRUMENTED:
            continue
        try:
            instrumentor = _load_instrumentor(module_path, class_name)
            if getattr(instrumentor, "is_instrumented_by_opentelemetry", False):
                _INSTRUMENTED.add(name)
                continue
            instrumentor.instrument(tracer_provider=tracer_provider)
            _INSTRUMENTED.add(name)
        except Exception as exc:  # noqa: BLE001 - nunca tumbar la app por instrumentación
            logger.warning(
                "No se pudo instrumentar %s para OpenTelemetry (%s).",
                name,
                type(exc).__name__,
            )


def init_telemetry(
    service_name: str | None = None,
    *,
    span_exporter: Any | None = None,
    force: bool = False,
) -> bool:
    """
    Inicializa OpenTelemetry cuando ``OTEL_ENABLED`` está activo (o ``force=True``).

    Cuando ``OTEL_ENABLED`` es falso (comportamiento por defecto), es un no-op puro:
    no instancia ``BatchSpanProcessor``, no abre sockets ni modifica loggers/handlers.
    """
    global _ACTIVE_PROVIDER, _INITIALIZED

    if not force and not is_telemetry_enabled():
        return False

    with _LOCK:
        if _INITIALIZED and span_exporter is None:
            return True

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        except Exception as exc:  # pragma: no cover - deps fijadas en requirements.txt
            logger.warning("Dependencias SDK de OpenTelemetry no disponibles (%s).", type(exc).__name__)
            return False

        resolved_service = (service_name or os.environ.get("OTEL_SERVICE_NAME") or "").strip() or "omni-erp"
        resolved_env = (
            os.environ.get("OTEL_ENVIRONMENT")
            or os.environ.get("RAILWAY_ENVIRONMENT")
            or os.environ.get("DJANGO_ENV")
            or "development"
        ).strip() or "development"

        resource = Resource.create(
            {
                "service.name": resolved_service,
                "deployment.environment": resolved_env,
            }
        )
        provider = TracerProvider(resource=resource)

        if span_exporter is not None:
            try:
                provider.add_span_processor(SimpleSpanProcessor(span_exporter))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "No se pudo registrar span_exporter de OpenTelemetry (%s); tracing local sin exportación.",
                    type(exc).__name__,
                )
        else:
            endpoint = _resolve_valid_otlp_endpoint()
            if endpoint is None:
                logger.warning(
                    "OTEL_ENABLED activo sin OTEL_EXPORTER_OTLP_ENDPOINT válido; "
                    "tracing local habilitado sin exportación de red."
                )
            else:
                try:
                    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                    exporter = OTLPSpanExporter()
                    provider.add_span_processor(BatchSpanProcessor(exporter))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "No se pudo inicializar el exportador OTLP (%s); tracing local sin exportación de red.",
                        type(exc).__name__,
                    )

        current_provider = trace.get_tracer_provider()
        if not isinstance(current_provider, TracerProvider):
            trace.set_tracer_provider(provider)

        _ACTIVE_PROVIDER = provider
        _INITIALIZED = True
        _instrument_libraries(provider)
        return True


configure_telemetry = init_telemetry


def shutdown_telemetry() -> None:
    """Hace flush y cierra limpiamente el TracerProvider activo si existe."""
    with _LOCK:
        provider = _ACTIVE_PROVIDER
        if provider is None:
            return
        try:
            if hasattr(provider, "force_flush"):
                provider.force_flush()
            if hasattr(provider, "shutdown"):
                provider.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error controlado al cerrar TracerProvider (%s).", type(exc).__name__)


def reset_telemetry_for_tests() -> None:
    """Restaura instrumentadores y TracerProvider global entre tests."""
    global _ACTIVE_PROVIDER, _INITIALIZED
    with _LOCK:
        for name, module_path, class_name in _INSTRUMENTOR_TARGETS:
            try:
                instrumentor = _load_instrumentor(module_path, class_name)
                if getattr(instrumentor, "is_instrumented_by_opentelemetry", False):
                    instrumentor.uninstrument()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error controlado al desinstrumentar %s (%s).", name, type(exc).__name__)

        _INSTRUMENTED.clear()
        shutdown_telemetry()
        _ACTIVE_PROVIDER = None
        _INITIALIZED = False

        try:
            from opentelemetry import trace as otel_trace

            once = getattr(otel_trace, "_TRACER_PROVIDER_SET_ONCE", None)
            if once is not None and hasattr(once, "_lock") and hasattr(once, "_done"):
                with once._lock:
                    otel_trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
                    once._done = False  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass


def _get_tracer(name: str = "apps.core.telemetry") -> Any:
    if _ACTIVE_PROVIDER is not None:
        return _ACTIVE_PROVIDER.get_tracer(name)
    from opentelemetry import trace

    return trace.get_tracer(name)


def _sanitize_header_text(raw: Any, *, max_len: int) -> str | None:
    """Convierte bytes/str de header a texto seguro rechazando NUL, saltos de línea y longitudes excesivas."""
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None
    elif isinstance(raw, str):
        text = raw
    else:
        return None

    if not text or "\x00" in text or "\r" in text or "\n" in text:
        return None
    if len(text) > max_len:
        return None
    return text


def inject_trace_headers(headers: Mapping[str, Any] | None = None) -> dict[str, str]:
    """
    Inyecta cabeceras W3C TraceContext (``traceparent``/``tracestate``) cuando hay tracing activo.

    Preserva cabeceras existentes seguras en un nuevo ``dict[str, str]``; tolera ``None``,
    valores binarios UTF-8 y entradas malformadas/NUL sin lanzar excepciones.
    """
    carrier: dict[str, str] = {}
    if isinstance(headers, Mapping):
        for raw_key, raw_val in headers.items():
            key = _sanitize_header_text(raw_key, max_len=_MAX_HEADER_KEY_LEN)
            val = _sanitize_header_text(raw_val, max_len=_MAX_HEADER_VAL_LEN)
            if key is not None and val is not None and key.strip():
                carrier[key] = val

    if not (is_telemetry_enabled() or is_telemetry_active()):
        return carrier

    try:
        from opentelemetry import trace
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        span = trace.get_current_span()
        span_ctx = span.get_span_context() if span is not None else None
        if span_ctx is not None and span_ctx.is_valid:
            TraceContextTextMapPropagator().inject(carrier)
    except Exception:  # noqa: BLE001 - propagación nunca debe romper negocio
        pass
    return carrier


def extract_trace_context(
    headers: Mapping[str, Any] | Iterable[tuple[Any, Any]] | None,
) -> Any:
    """
    Extrae un ``Context`` W3C TraceContext desde cabeceras HTTP o Kafka (``dict`` o lista de tuplas).

    Tolerante a ``None``, formatos ``bytes``/``str``, NUL (``\\x00``), longitudes inválidas y
    valores malformados: retorna ``None`` sin lanzar excepciones cuando no hay contexto válido.
    """
    if not (is_telemetry_enabled() or is_telemetry_active()) or headers is None:
        return None

    if isinstance(headers, Mapping):
        items: Iterable[Any] = headers.items()
    elif isinstance(headers, (str, bytes, bytearray)):
        return None
    elif isinstance(headers, Iterable):
        items = headers
    else:
        return None

    normalized: dict[str, str] = {}
    try:
        for item in items:
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            raw_key, raw_val = item
            key = _sanitize_header_text(raw_key, max_len=_MAX_HEADER_KEY_LEN)
            val = _sanitize_header_text(raw_val, max_len=_MAX_HEADER_VAL_LEN)
            if key is None or val is None:
                continue
            key_lower = key.strip().lower()
            if key_lower in {"traceparent", "tracestate"}:
                normalized[key_lower] = val.strip()
    except Exception:  # noqa: BLE001
        return None

    if "traceparent" not in normalized:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        ctx = TraceContextTextMapPropagator().extract(carrier=normalized)
        span = trace.get_current_span(ctx)
        if span is not None and span.get_span_context().is_valid:
            return ctx
    except Exception:  # noqa: BLE001
        return None
    return None


def _resolve_span_kind(span_kind: Any) -> Any:
    from opentelemetry.trace import SpanKind

    if isinstance(span_kind, SpanKind):
        return span_kind
    if isinstance(span_kind, str):
        mapping = {
            "internal": SpanKind.INTERNAL,
            "server": SpanKind.SERVER,
            "client": SpanKind.CLIENT,
            "producer": SpanKind.PRODUCER,
            "consumer": SpanKind.CONSUMER,
        }
        return mapping.get(span_kind.strip().lower(), SpanKind.INTERNAL)
    return SpanKind.INTERNAL


class trazar_operacion(ContextDecorator):
    """
    Decorador y context manager opt-in para envolver operaciones con un span OpenTelemetry.

    Cuando la telemetría está desactivada es un no-op puro. Cuando está activa, filtra y sanea
    cualquier atributo con llave sensible (``token``, ``secret``, ``password``, ``api_key``, etc.)
    conforme a R-CODE-8 y evita propagar mensajes de excepción/tracebacks en atributos del span.
    """

    def __init__(
        self,
        nombre: str,
        *,
        context: Any = None,
        span_kind: Any = None,
        **atributos: Any,
    ) -> None:
        self.nombre = (nombre or "operacion").strip() or "operacion"
        self._context = context
        self._span_kind = span_kind
        self._atributos = atributos
        self._cm: AbstractContextManager[Any] | None = None
        self._span: Any = None

    def _recreate_cm(self) -> trazar_operacion:
        return trazar_operacion(
            self.nombre,
            context=self._context,
            span_kind=self._span_kind,
            **self._atributos,
        )

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:  # type: ignore[override]
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_inner(*args: Any, **kwargs: Any) -> Any:
                with self._recreate_cm():
                    return await func(*args, **kwargs)

            return async_inner

        @functools.wraps(func)
        def sync_inner(*args: Any, **kwargs: Any) -> Any:
            with self._recreate_cm():
                return func(*args, **kwargs)

        return sync_inner

    def __enter__(self) -> Any:
        if not (is_telemetry_enabled() or is_telemetry_active()):
            cm: AbstractContextManager[Any] = nullcontext(None)
            self._cm = cm
            self._span = None
            return cm.__enter__()

        from opentelemetry.context import Context

        attrs = dict(self._atributos)
        otel_ctx: Context | None = None
        if self._context is not None:
            if isinstance(self._context, Context):
                otel_ctx = self._context
            else:
                attrs["context"] = self._context

        safe_attrs = sanitize_span_attributes(attrs)
        kind = _resolve_span_kind(self._span_kind)
        tracer = _get_tracer("apps.core.telemetry")
        span_cm: AbstractContextManager[Any] = tracer.start_as_current_span(
            self.nombre,
            context=otel_ctx,
            kind=kind,
            attributes=safe_attrs,
            record_exception=False,
            set_status_on_exception=False,
        )
        self._cm = span_cm
        self._span = span_cm.__enter__()
        return self._span

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        cm = self._cm
        if cm is None:
            return False
        if exc_type is not None and self._span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode

                self._span.set_attribute("error.type", exc_type.__name__)
                self._span.set_status(Status(StatusCode.ERROR, exc_type.__name__))
            except Exception:  # noqa: BLE001
                pass
        try:
            return bool(cm.__exit__(exc_type, exc_val, exc_tb))
        finally:
            self._cm = None
            self._span = None


class OTelTraceLogFilter(logging.Filter):
    """
    Filtro de logging que inyecta ``record.trace_id`` (32 hex o ``"-"``) y
    ``record.span_id`` (16 hex o ``"-"``) sin registrar payloads, PII ni secretos.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = "-"
        span_id = "-"
        if is_telemetry_enabled() or is_telemetry_active():
            try:
                from opentelemetry import trace

                span = trace.get_current_span()
                span_ctx = span.get_span_context() if span is not None else None
                if span_ctx is not None and span_ctx.is_valid:
                    trace_id = f"{span_ctx.trace_id:032x}"
                    span_id = f"{span_ctx.span_id:016x}"
            except Exception:  # noqa: BLE001
                trace_id = "-"
                span_id = "-"
        record.trace_id = trace_id
        record.span_id = span_id
        return True
