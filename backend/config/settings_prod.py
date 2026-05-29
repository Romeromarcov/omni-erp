from .settings_base import *  # noqa: F401, F403

DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

# CORS — solo orígenes explícitos en producción
CORS_ALLOW_ALL_ORIGINS = False

# Guardia de seguridad SEC-06: si por cualquier motivo CORS_ALLOW_ALL_ORIGINS
# termina siendo True (ej: settings_base cargado con DEBUG=True accidentalmente),
# esta línea detiene el arranque del servidor en lugar de silenciosamente abrir CORS.
if CORS_ALLOW_ALL_ORIGINS:
    raise ValueError(
        "CORS_ALLOW_ALL_ORIGINS=True no está permitido en producción. "
        "Verifique que DEBUG=False y que settings_prod.py esté siendo cargado correctamente."
    )
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()
]

# HTTPS security headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# Logs solo INFO en producción (no DEBUG)
LOGGING["handlers"]["console"]["level"] = "INFO"  # noqa: F821

# ── Sentry (GAP-10) ─────────────────────────────────────────────────────────
# Configurar SENTRY_DSN en el entorno de producción para habilitar el monitoreo.
# Si SENTRY_DSN no está definido, Sentry permanece deshabilitado.
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    import logging as _logging

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
                signals_spans=False,
            ),
            CeleryIntegration(monitor_beat_tasks=True),
            LoggingIntegration(
                level=_logging.INFO,        # captura INFO y superiores como breadcrumbs
                event_level=_logging.ERROR, # envía ERROR y superiores como eventos
            ),
        ],
        # Porcentaje de transacciones enviadas a Sentry Performance.
        # Ajustar según el tráfico real en producción.
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        # Porcentaje de sesiones de usuario capturadas.
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.05")),
        environment="production",
        send_default_pii=False,  # SEC: nunca enviar datos personales identificables
    )
