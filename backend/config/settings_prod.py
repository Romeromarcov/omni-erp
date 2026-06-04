from .settings_base import *  # noqa: F401, F403

DEBUG = False
# M-SEC-14: ALLOWED_HOSTS no puede quedar vacío en producción. Fail-closed.
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
# Railway: la plataforma SIEMPRE inyecta RAILWAY_ENVIRONMENT en el contenedor.
# Cuando está presente, permitimos los dominios de Railway para que el deploy
# funcione aunque la propagación de DJANGO_ALLOWED_HOSTS al contenedor falle
# (ver docs/_archive/RAILWAY_TROUBLESHOOTING_2026-06-03.md). El comodín
# ".up.railway.app" cubre el dominio público asignado por Railway.
if os.environ.get("RAILWAY_ENVIRONMENT"):
    # localhost/127.0.0.1: NECESARIOS para el HEALTHCHECK del contenedor
    # (`curl http://localhost:$PORT/api/health/` → Host: localhost). Sin ellos el
    # healthcheck da DisallowedHost, el contenedor queda "unhealthy" y Railway no
    # promueve el deploy nuevo (sigue sirviendo uno viejo).
    for _rh in (".up.railway.app", ".railway.app", ".railway.internal",
                "localhost", "127.0.0.1",
                os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip(),
                os.environ.get("RAILWAY_PRIVATE_DOMAIN", "").strip()):
        if _rh and _rh not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_rh)
if not ALLOWED_HOSTS:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS debe definir al menos un host en producción "
        "(ej: 'midominio.com,www.midominio.com')."
    )

# Diagnóstico de arranque (temporal): deja en los logs qué ALLOWED_HOSTS resolvió
# el contenedor. Útil para confirmar la propagación de variables en Railway.
import sys as _sys  # noqa: E402
print(f"[settings_prod] DJANGO_ENV={os.environ.get('DJANGO_ENV')!r} "
      f"RAILWAY_ENVIRONMENT={os.environ.get('RAILWAY_ENVIRONMENT')!r} "
      f"DJANGO_ALLOWED_HOSTS_env={os.environ.get('DJANGO_ALLOWED_HOSTS')!r} "
      f"ALLOWED_HOSTS={ALLOWED_HOSTS}", file=_sys.stderr, flush=True)

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
