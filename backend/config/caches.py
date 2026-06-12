"""Construcción de ``CACHES["default"]`` — P2-4 del plan 05 (hardening).

Por qué existe este módulo
==========================
Hasta P2-4, ``CACHES`` quedaba en el default de Django (LocMem **por proceso**).
Todo lo que guarda estado en el cache ``default`` —rate-limiting de login
(django-ratelimit, SEC-07), throttling global de DRF (P1-1) y el futuro circuit
breaker del gateway LLM (P2-1)— contaba por *worker* de uvicorn en producción:
con N workers, los límites efectivos se multiplicaban por N. Con Redis como
backend compartido, los contadores son únicos por instancia/entorno.

Reglas de diseño (ver tests en ``tests_api/test_p24_caches_redis.py``):

* **Con ``REDIS_URL``** → ``django.core.cache.backends.redis.RedisCache``
  (backend nativo de Django 4.0+; no requiere ``django-redis``) sobre una **DB
  de Redis distinta** de la del broker de Celery (que usa ``REDIS_URL`` tal
  cual, DB 0 por convención). Mezclar keyspaces sería peligroso:
  ``cache.clear()`` ejecuta ``FLUSHDB`` y vaciaría la cola de Celery.
  La colisión de DBs es un error de configuración → ``ImproperlyConfigured``
  (fail-closed al arrancar, no corrupción silenciosa en runtime).
* **Sin ``REDIS_URL``** → LocMem, para que el dev local funcione sin Redis.
* **Bajo pytest** → LocMem SIEMPRE, aunque haya ``REDIS_URL``: el CI define
  ``REDIS_URL`` para satisfacer settings pero NO levanta un servicio Redis en
  los jobs de pytest (Celery corre ALWAYS_EAGER), y los tests de
  throttle/ratelimit/idempotencia necesitan un cache determinista y aislado
  por proceso. Los jobs de CI con servidor vivo (e2e, contract) SÍ levantan un
  service de Redis y ejercitan este path real.

Nota operativa (aceptada a conciencia): con Redis caído, ratelimit (SEC-07) y
throttling DRF fallan CERRADO (5xx) — el mismo blast-radius que ya tiene el
broker de Celery, gestionado por Railway por entorno. Un fail-open silencioso
sería un bypass del rate-limiting, peor que la indisponibilidad.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ImproperlyConfigured

#: Fallback sin Redis (dev local / suite de tests). LOCATION fija para que
#: todos los imports del proceso compartan la misma instancia LocMem.
LOCMEM_CACHE: dict = {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "omni-erp-default",
}


def redis_db_from_url(redis_url: str) -> str:
    """DB que usa una URL de Redis: path ``/N``, o ``?db=N``, o ``0`` (default).

    Es la misma convención que aplican redis-py y Kombu (broker de Celery):
    sin path ni query, la conexión va a la DB 0.
    """
    parts = urlsplit(redis_url)
    path_db = parts.path.strip("/")
    if path_db:
        return path_db
    query_db = dict(parse_qsl(parts.query)).get("db")
    return query_db or "0"


def build_default_cache(
    redis_url: str,
    *,
    testing: bool,
    cache_db: str,
    key_prefix: str,
) -> dict:
    """Config de ``CACHES["default"]`` según entorno (ver módulo arriba).

    :param redis_url: valor de ``REDIS_URL`` ("" o None → LocMem).
    :param testing: True bajo pytest → fuerza LocMem (determinismo en CI).
    :param cache_db: DB de Redis para el cache (distinta de la de Celery).
    :param key_prefix: ``KEY_PREFIX`` por entorno (higiene/observabilidad).
    """
    if testing or not redis_url:
        return dict(LOCMEM_CACHE)

    try:
        db_num = int(cache_db)
    except (TypeError, ValueError):
        raise ImproperlyConfigured(
            f"REDIS_CACHE_DB debe ser un entero (DB de Redis), recibido: {cache_db!r}."
        ) from None

    celery_db = redis_db_from_url(redis_url)
    if str(db_num) == celery_db:
        raise ImproperlyConfigured(
            f"REDIS_CACHE_DB={db_num} colisiona con la DB del broker de Celery "
            f"(REDIS_URL usa la DB {celery_db}). El cache de Django debe vivir en "
            "una DB distinta: cache.clear() hace FLUSHDB y vaciaría la cola de "
            "Celery. Configurá REDIS_CACHE_DB con otra DB."
        )

    parts = urlsplit(redis_url)
    # La DB del cache va en el path; si la URL traía ?db=N se descarta para que
    # no compita con el path (redis-py acepta ambos — evitamos la ambigüedad).
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "db"])
    location = urlunsplit(
        (parts.scheme, parts.netloc, f"/{db_num}", query, parts.fragment)
    )
    return {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": location,
        "KEY_PREFIX": key_prefix,
    }
