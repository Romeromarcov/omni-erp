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
