import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")

# H-SEC-4: clave Fernet para cifrar campos sensibles (EncryptedJSONField).
# En producción se DEBE configurar CRYPTOGRAPHY_KEY explícito y rotarla aparte
# del SECRET_KEY; si no está, se deriva del SECRET_KEY (aceptable solo en dev).
CRYPTOGRAPHY_KEY = os.environ.get("CRYPTOGRAPHY_KEY")

# M-SEC-3: SameSite del refresh_token httpOnly. Default "Strict" (más seguro).
# Si el frontend vive en un dominio/subdominio distinto del backend (p. ej.
# servicios separados en Railway), poné "None" en el entorno (requiere Secure,
# que ya se aplica en prod) para que el refresh cross-site funcione.
REFRESH_TOKEN_COOKIE_SAMESITE = os.environ.get(
    "REFRESH_TOKEN_COOKIE_SAMESITE", "Strict"
)

DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
).split(",")

INSTALLED_APPS = [
    "drf_yasg",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
    "storages",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    # P1-3 hardening: bloqueo de cuenta por usuario+IP tras N fallos de login
    "axes",
    # Apps ERP
    "apps.core",
    "apps.localizacion",  # GAP-2 / ADR-007: framework de localización (puertos)
    "apps.finanzas",
    "apps.fiscal",
    "apps.contabilidad",
    "apps.gastos",
    "apps.nomina",
    "apps.control_asistencia",
    "apps.servicio_cliente",
    "apps.inventario",
    "apps.almacenes",
    "apps.proveedores",
    "apps.compras",
    "apps.cuentas_por_pagar",
    "apps.crm",
    "apps.ventas",
    "apps.cuentas_por_cobrar",
    "apps.cxc",
    "apps.manufactura",
    "apps.rrhh",
    "apps.tesoreria",
    "apps.banca_electronica",
    "apps.configuracion_motor",
    "apps.auditoria",
    "apps.gestion_documental",
    "apps.gestion_aprobaciones",
    "apps.integracion_b2b",
    "apps.integration_hub",
    "apps.migracion_datos",
    "apps.despacho",
    "apps.costos",
    "apps.agentes",
    "apps.personalizacion",
    "apps.notificaciones",
    "apps.saas",
    # Event Store
    "apps.eventos",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise debe ir inmediatamente después de SecurityMiddleware para
    # servir los estáticos (CSS/JS del admin incluidos) en producción.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # RLS: fija el contexto multi-tenant en la conexión tras autenticar.
    # Se descarta solo (MiddlewareNotUsed) si RLS_ENABLED es False.
    "apps.core.middleware.RLSContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # SaaS (Plan C — C2): verificación de suscripción activa. Inerte salvo que
    # SAAS_VERIFICAR_SUSCRIPCION=True. Va al final para resolver el usuario JWT.
    "apps.saas.middleware.SuscripcionActivaMiddleware",
    # P1-3: django-axes debe ir lo más al final posible (tras autenticación)
    # para registrar intentos fallidos y responder al lockout.
    "axes.middleware.AxesMiddleware",
]

# ── P1-3 · django-axes — bloqueo de cuenta por usuario+IP ────────────────────
# Bloquea la COMBINACIÓN usuario+IP tras AXES_FAILURE_LIMIT intentos fallidos.
# Combinado (no "o"): un atacante distribuido no bloquea al usuario legítimo
# desde su propia IP, y un atacante desde una IP no queda libre probando otros
# usuarios sin costo. Los mensajes al cliente son genéricos (no filtran si el
# usuario existe) — ver apps/core/auth_views.py.
AXES_ENABLED = os.environ.get("AXES_ENABLED", "True") == "True"
# 10 fallos (no 5): el rate-limit SEC-07 (5/min por IP) ya frena el burst; axes
# cubre la fuerza bruta LENTA acumulada contra un usuario. Con 5 ambos umbrales
# colisionarían (el 5to intento daría lockout en vez del 401 que SEC-07 garantiza).
AXES_FAILURE_LIMIT = int(os.environ.get("AXES_FAILURE_LIMIT", "10"))
AXES_COOLOFF_TIME = timedelta(
    minutes=int(os.environ.get("AXES_COOLOFF_MINUTES", "15"))
)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True  # login exitoso limpia el contador de fallos
# Respuesta JSON 429 genérica al lockout (el default de axes es HTML).
AXES_LOCKOUT_CALLABLE = "apps.core.auth_views.axes_lockout_response"

# SaaS — control de acceso por pago (Plan C — Fase C2).
# Off por defecto (fail-open). Se activa primero en staging para validar el
# flujo 402 end-to-end antes de producción.
SAAS_VERIFICAR_SUSCRIPCION = (
    os.environ.get("SAAS_VERIFICAR_SUSCRIPCION", "False") == "True"
)

# --- Row Level Security (P0-1 plan de hardening) ---
# Gobierna únicamente si el middleware aplica el enforcement por request. Las
# políticas RLS y el contexto por defecto de conexión existen siempre (ver
# apps/core/rls.py). Activar gradualmente: staging antes que producción.
RLS_ENABLED = os.environ.get("RLS_ENABLED", "False").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Soporte de DATABASE_URL (Railway/Heroku inyectan un solo connection string).
# Si está presente, tiene prioridad; si no, se usan las variables DB_* (dev local).
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    from urllib.parse import unquote, urlparse

    _u = urlparse(_database_url)
    if _u.scheme not in ("postgres", "postgresql"):
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            f"DATABASE_URL debe ser PostgreSQL (postgres://), recibido: {_u.scheme}://"
        )
    _db_config = {
        "NAME": (_u.path or "/omni_erp").lstrip("/"),
        "USER": unquote(_u.username or ""),
        "PASSWORD": unquote(_u.password or ""),
        "HOST": _u.hostname or "",
        "PORT": str(_u.port or "5432"),
    }
else:
    _db_host = os.environ.get("DB_HOST")
    if not _db_host:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "Falta DATABASE_URL o DB_HOST. "
            "Omni ERP requiere PostgreSQL — SQLite no está soportado. "
            "En Railway: enlazá el plugin Postgres (provee DATABASE_URL). "
            "En local: copiá .env.example a .env y completá las variables DB_*."
        )
    _db_config = {
        "NAME": os.environ.get("DB_NAME", "omni_erp"),
        "USER": os.environ.get("DB_USER", "omni_erp"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": _db_host,
        "PORT": os.environ.get("DB_PORT", "5432"),
    }

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        **_db_config,
        "OPTIONS": {
            "connect_timeout": 5,
            "client_encoding": "UTF8",
        },
    }
}

# Nombre de la BD de test sobreescribible por entorno (TEST_DB_NAME). Permite
# correr suites en paralelo (varios worktrees/agentes contra el mismo Postgres)
# sin pelearse por el default "test_<DB_NAME>".
_test_db_name = os.environ.get("TEST_DB_NAME")
if _test_db_name:
    DATABASES["default"]["TEST"] = {"NAME": _test_db_name}

# P1-3: política de contraseñas reforzada. Mínimo 12 caracteres (NIST 800-63B
# recomienda priorizar longitud sobre complejidad artificial) + los validadores
# estándar de Django (similitud con atributos, contraseñas comunes, numéricas).
PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "12"))

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "core.Usuarios"

LANGUAGE_CODE = "es-ve"
TIME_ZONE = "America/Caracas"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Almacenamiento de estáticos: WhiteNoise comprime y cachea los archivos que
# `collectstatic` deja en STATIC_ROOT (CSS/JS del admin incluidos). El backend
# de `default` (archivos subidos por usuarios) se sobreescribe a S3 más abajo
# cuando USE_S3=True. Usamos CompressedStaticFilesStorage (sin manifest con
# hash) para no romper el build si algún template referencia un estático ausente.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CORS_ALLOW_CREDENTIALS = True

# Django REST Framework settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # P1-1 Hardening: Throttling global DRF (capa de defensa en profundidad).
    # El login/token ya tiene su propio rate-limit via django-ratelimit (SEC-07,
    # 5/min por IP). Estas tasas son GENEROSAS a propósito para no interferir con
    # la suite de tests (que hace muchas requests dentro del mismo test) ni con
    # usuarios legítimos en producción. El objetivo es proteger contra scraping
    # masivo y ataques de fuerza bruta en endpoints no protegidos por SEC-07.
    #
    # Tasas elegidas:
    #   anon   100/min  — visitantes sin sesión (p. ej. health, schema público).
    #                     100 req/min = ~1.7 req/s, suficiente para monitoreo.
    #   user   1000/min — usuarios autenticados. Un ERP en uso normal genera
    #                     decenas de requests por operación (listados + filtros);
    #                     1000/min deja margen amplio incluso para automatizaciones.
    #   signup 10/hour  — scope preexistente para el registro público de SaaS
    #                     (apps/saas/views.py declara throttle_scope='signup').
    #                     NO borrar: sin esta clave DRF lanza ImproperlyConfigured.
    #
    # Para endpoints de mayor riesgo (escritura masiva, importación, exportación)
    # se puede añadir un throttle_scope por vista, sin tocar estas tasas base.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    # Las tasas son configurables por entorno (THROTTLE_RATE_*) para poder
    # ajustarlas en staging/producción sin redeploy de código.
    # 'escritura' es el scope más estricto para endpoints de escritura/pago
    # (apps.core.throttling.EscrituraRateThrottle — solo cuenta métodos no
    # seguros: POST/PUT/PATCH/DELETE).
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_RATE_ANON", "100/min"),
        "user": os.environ.get("THROTTLE_RATE_USER", "1000/min"),
        "signup": os.environ.get("THROTTLE_RATE_SIGNUP", "10/hour"),
        "escritura": os.environ.get("THROTTLE_RATE_ESCRITURA", "60/min"),
    },
}

# drf-yasg — DEFAULT_INFO permite `manage.py generate_swagger` (esquema OpenAPI
# para el contract testing con schemathesis). USE_COMPAT_RENDERERS=False silencia
# el warning de renderers y alinea el formato.
SWAGGER_SETTINGS = {
    "DEFAULT_INFO": "config.urls.api_info",
    "USE_SESSION_AUTH": False,
}

# JWT Settings
SIMPLE_JWT = {
    # M-SEC-4: access token corto (15 min); el refresh httpOnly (7d) renueva.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=60),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=7),
}

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "formatter": "verbose",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "omni.eventos": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# Create logs directory if it doesn't exist
os.makedirs(BASE_DIR / "logs", exist_ok=True)

AUTHENTICATION_BACKENDS = [
    # P1-3: AxesStandaloneBackend va PRIMERO — corta el authenticate() cuando
    # la combinación usuario+IP está bloqueada (lanza PermissionDenied, que
    # django.contrib.auth.authenticate traduce a None → credenciales inválidas,
    # sin filtrar la existencia del usuario).
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ─────────────────────────────────────────────────────────────────
# Almacenamiento de archivos — S3-compatible (MinIO en dev, S3 en prod)
# ─────────────────────────────────────────────────────────────────
USE_S3 = os.environ.get("USE_S3", "False") == "True"

if USE_S3:
    # Backend S3-compatible (funciona con MinIO, AWS S3, Cloudflare R2, etc.)
    # Solo se sobreescribe "default" (archivos subidos por usuarios); los
    # estáticos siguen sirviéndose con WhiteNoise (ver STORAGES más arriba).
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    }

    # Credenciales S3 / MinIO.
    # M-SEC-12: en dev se permite el default minioadmin; en prod (DEBUG=False)
    # se exige el valor explícito en el entorno (fail-closed) para no firmar/
    # acceder al storage con credenciales conocidas.
    if DEBUG:
        AWS_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY", "minioadmin")
        AWS_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin")
    else:
        try:
            AWS_ACCESS_KEY_ID = os.environ["S3_ACCESS_KEY"]
            AWS_SECRET_ACCESS_KEY = os.environ["S3_SECRET_KEY"]
        except KeyError as exc:
            from django.core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured(
                f"En producción con USE_S3=True, {exc.args[0]} debe estar en el entorno "
                "(no se permite el default 'minioadmin')."
            ) from exc
    AWS_STORAGE_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "omni-erp")
    AWS_S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
    AWS_S3_REGION_NAME = os.environ.get("S3_REGION", "us-east-1")

    # Seguridad: los archivos no son públicos por defecto
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True  # URLs firmadas (presigned)
    AWS_QUERYSTRING_EXPIRE = 3600  # 1 hora
    AWS_S3_FILE_OVERWRITE = False  # evitar sobreescritura silenciosa
    AWS_S3_SIGNATURE_VERSION = "s3v4"

    # Usar path-style para MinIO (virtual-hosted no está disponible en dev)
    AWS_S3_ADDRESSING_STYLE = "path"

    # Prefijo raíz para todos los archivos subidos por Django
    # (los archivos de tenant usarán empresa_id como prefijo adicional)
    AWS_LOCATION = "media"

    MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/media/"

else:
    # Almacenamiento local — para desarrollo sin MinIO levantado
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"

# Variables exportadas para que StorageService pueda leer sin importar settings
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "omni-erp")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
S3_PRESIGNED_URL_EXPIRES = int(os.environ.get("S3_PRESIGNED_URL_EXPIRES", "3600"))

# ─────────────────────────────────────────────────────────────────
# Celery — broker Redis, resultados en Django DB
# ─────────────────────────────────────────────────────────────────
_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CELERY_BROKER_URL = _redis_url
CELERY_RESULT_BACKEND = "django-db"  # persiste en django_celery_results
CELERY_CACHE_BACKEND = "default"

# Serialización
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# Zona horaria coherente con Django
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Reintentos: no perder tareas si Redis está momentáneamente caído
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Límite suave de tiempo por tarea (segundos) — previene tareas zombis
CELERY_TASK_SOFT_TIME_LIMIT = 300  # 5 min
CELERY_TASK_TIME_LIMIT = 600  # 10 min (hard kill)

# Beat — schedule de tareas periódicas
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Hub CxC — Sync automático de tasas venezolanas y cartera
# (Puede sobreescribirse en la DB vía django-celery-beat admin)
from celery.schedules import crontab as _crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # BCV sync — 9:00 AM Venezuela (UTC-4 = 13:00 UTC)
    "hub-sync-tasas-bcv-manana": {
        "task": "integration_hub.sync_tasas_ve",
        "schedule": _crontab(hour=13, minute=0),
    },
    # BCV sync — 3:00 PM Venezuela (UTC-4 = 19:00 UTC)
    "hub-sync-tasas-bcv-tarde": {
        "task": "integration_hub.sync_tasas_ve",
        "schedule": _crontab(hour=19, minute=0),
    },
    # Binance P2P — cada 30 minutos
    "hub-sync-binance-p2p": {
        "task": "integration_hub.sync_tasas_ve",
        "schedule": _crontab(minute="*/30"),
    },
    # Limpieza de logs de integración — diaria a las 2 AM UTC
    "hub-limpiar-logs-antiguos": {
        "task": "integration_hub.limpiar_logs_antiguos",
        "schedule": _crontab(hour=2, minute=0),
        "kwargs": {"dias": 30},
    },
    # Sync inbound por conector según su intervalo (pagos/contactos/…) — Plan D D2.
    # Cada instancia decide su cadencia con intervalo_sync_minutos; esta tarea solo
    # despierta cada 15 min y dispara las que ya vencieron.
    "hub-sync-automatico-conectores": {
        "task": "integration_hub.sync_automatico_todos",
        "schedule": _crontab(minute="*/15"),
    },
    # Export outbound automático a Google Sheets según intervalo del destino — PR 3.
    # Cada instancia Sheets decide su cadencia con intervalo_sync_minutos; esta
    # tarea despierta cada 15 min y dispara las que ya vencieron.
    "export-sheets-automatico": {
        "task": "integration_hub.export_automatico_todos",
        "schedule": _crontab(minute="*/15"),
    },
    # Refresco de cache de cartera vencida para tenants Mode A (Odoo) — Plan D D2.
    "hub-sync-cartera-odoo": {
        "task": "integration_hub.sync_cartera_odoo_todos",
        "schedule": _crontab(minute="*/30"),
    },
}

# ── Event Store (Redpanda/Kafka) ───────────────────────────────────────────────
# Dejar KAFKA_BROKER_URL vacío para deshabilitar (degradación graceful a log).
# En producción: KAFKA_BROKER_URL=redpanda:9092
KAFKA_BROKER_URL = os.environ.get("KAFKA_BROKER_URL", "")  # vacío = deshabilitado
KAFKA_TOPIC_PREFIX = os.environ.get("KAFKA_TOPIC_PREFIX", "omni")
KAFKA_PRODUCER_CONFIG = {
    "bootstrap.servers": KAFKA_BROKER_URL,
    "client.id": "omni-erp-producer",
    "acks": "all",  # máxima durabilidad
    "retries": 3,
}

# ── MCP Agent Capabilities ─────────────────────────────────────────────────────
# Controla qué módulos se registran en el servidor MCP y con qué scopes.
# Los module_paths se importan automáticamente al iniciar mcp_server.py.
# Para añadir un módulo: agregar su ruta a module_paths.
MCP_AGENT_CAPABILITIES: dict = {
    "server_name": "omni-erp",
    "server_version": "0.1.0",
    "module_paths": [
        "apps.ventas.mcp",
        "apps.inventario.mcp",
        "apps.finanzas.mcp",
        "apps.manufactura.mcp",
    ],
    "scopes": {
        "core:read": "Lectura de empresas y clientes",
        "crm:read": "Lectura del CRM (clientes, contactos)",
        "ventas:read": "Lectura de pedidos, cotizaciones, facturas",
        "ventas:write": "Creación y modificación de pedidos",
        "inventario:read": "Consulta de stock y movimientos",
        "inventario:write": "Registro de movimientos de inventario",
        "finanzas:read": "Consulta de pagos, cajas, monedas",
        "finanzas:write": "Registro de pagos y movimientos de caja",
        "fiscal:read": "Consulta de correlativos fiscales",
        "fiscal:write": "Emisión de documentos fiscales",
        "manufactura:read": "Consulta de OF, costeo real y MRP",
        "*": "Acceso completo (solo uso interno)",
    },
}
