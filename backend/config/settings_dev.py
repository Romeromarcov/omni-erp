import os

# H-SEC-2: NO usar un SECRET_KEY default débil. Si una instancia (incl. staging)
# arranca sin SECRET_KEY explícito, settings_base lanza un error claro en vez de
# firmar JWTs con una clave conocida. Copiá .env.example a .env y generá una clave.
os.environ.setdefault("DEBUG", "True")

from .settings_base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

CORS_ALLOW_ALL_ORIGINS = True

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
]

# Disable CSRF for DRF in dev (JWT doesn't need it, session auth is dev-only)
MIDDLEWARE = [m for m in MIDDLEWARE if "CsrfViewMiddleware" not in m]
