import os

from django.core.exceptions import ImproperlyConfigured

# H-SEC-1: fail-closed. Un typo como DJANGO_ENV=production (en vez de 'prod')
# NO debe caer silenciosamente a settings_dev (DEBUG + CORS abierto). Exigimos
# un valor explícito y válido.
env = os.environ.get("DJANGO_ENV")
if env not in ("dev", "prod"):
    raise ImproperlyConfigured(
        f"DJANGO_ENV debe ser 'dev' o 'prod', recibido: {env!r}. "
        "Configurá la variable de entorno explícitamente (ver .env.example)."
    )

if env == "prod":
    from .settings_prod import *
else:
    from .settings_dev import *
