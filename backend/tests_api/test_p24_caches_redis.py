"""P2-4 (plan 05 hardening) — ``CACHES`` de Django según entorno.

Cubre ``config/caches.py`` (builder puro, sin tocar red) y el invariante de la
suite: bajo pytest el cache default es SIEMPRE LocMem, aunque el entorno (CI)
defina ``REDIS_URL`` — el CI no levanta servicio Redis y los tests de
throttle/ratelimit/idempotencia necesitan contadores deterministas por proceso.
"""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from config.caches import LOCMEM_CACHE, build_default_cache, redis_db_from_url

pytestmark = pytest.mark.unit


class TestRedisDbFromUrl:
    """Convención redis-py/Kombu: DB en el path, o ``?db=``, o 0 por defecto."""

    def test_db_en_path(self):
        assert redis_db_from_url("redis://localhost:6379/3") == "3"

    def test_sin_path_es_db_cero(self):
        assert redis_db_from_url("redis://localhost:6379") == "0"

    def test_path_vacio_es_db_cero(self):
        assert redis_db_from_url("redis://localhost:6379/") == "0"

    def test_db_en_query(self):
        assert redis_db_from_url("redis://localhost:6379?db=2") == "2"

    def test_path_gana_sobre_query(self):
        assert redis_db_from_url("redis://localhost:6379/4?db=2") == "4"


class TestBuildDefaultCache:
    def test_sin_redis_url_cae_a_locmem(self):
        config = build_default_cache(
            "", testing=False, cache_db="1", key_prefix="omni:dev"
        )
        assert config == LOCMEM_CACHE
        # Copia defensiva: mutar el resultado no debe tocar el default del módulo.
        assert config is not LOCMEM_CACHE

    def test_testing_fuerza_locmem_aunque_haya_redis_url(self):
        """CI define REDIS_URL sin servidor Redis → bajo pytest, LocMem siempre."""
        config = build_default_cache(
            "redis://localhost:6379/0",
            testing=True,
            cache_db="1",
            key_prefix="omni:dev",
        )
        assert config == LOCMEM_CACHE

    def test_con_redis_url_usa_backend_redis_en_db_distinta(self):
        """Caso Railway: REDIS_URL en DB 0 (Celery) → cache en DB 1."""
        config = build_default_cache(
            "redis://default:pwd@redis.railway.internal:6379",
            testing=False,
            cache_db="1",
            key_prefix="omni:production",
        )
        assert config["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
        assert config["LOCATION"] == "redis://default:pwd@redis.railway.internal:6379/1"
        assert config["KEY_PREFIX"] == "omni:production"

    def test_preserva_esquema_credenciales_y_query(self):
        """rediss:// (TLS) con query extra se respeta; el ``db=`` de la query se
        descarta para que no compita con la DB del path."""
        config = build_default_cache(
            "rediss://default:pwd@host.example:6380?ssl_cert_reqs=none&db=5",
            testing=False,
            cache_db="2",
            key_prefix="omni:staging",
        )
        assert config["LOCATION"] == (
            "rediss://default:pwd@host.example:6380/2?ssl_cert_reqs=none"
        )

    def test_colision_con_db_de_celery_en_path_falla(self):
        with pytest.raises(ImproperlyConfigured, match="colisiona"):
            build_default_cache(
                "redis://localhost:6379/1",
                testing=False,
                cache_db="1",
                key_prefix="omni:dev",
            )

    def test_colision_con_db_cero_implicita_falla(self):
        """Sin path la URL apunta a la DB 0 → cache_db=0 es colisión."""
        with pytest.raises(ImproperlyConfigured, match="FLUSHDB"):
            build_default_cache(
                "redis://localhost:6379",
                testing=False,
                cache_db="0",
                key_prefix="omni:dev",
            )

    def test_colision_con_db_en_query_falla(self):
        with pytest.raises(ImproperlyConfigured, match="colisiona"):
            build_default_cache(
                "redis://localhost:6379?db=1",
                testing=False,
                cache_db="1",
                key_prefix="omni:dev",
            )

    def test_cache_db_no_numerica_falla(self):
        with pytest.raises(ImproperlyConfigured, match="entero"):
            build_default_cache(
                "redis://localhost:6379/0",
                testing=False,
                cache_db="uno",
                key_prefix="omni:dev",
            )


class TestCachesDeLaSuite:
    """Invariantes del entorno de test real (settings cargados por pytest)."""

    def test_suite_usa_locmem(self):
        """Determinismo: aunque CI exporte REDIS_URL (sin servidor), la suite
        corre con LocMem. Si esto falla, los tests de throttle/SEC-07 dejan de
        ser confiables."""
        backend = settings.CACHES["default"]["BACKEND"]
        assert backend == "django.core.cache.backends.locmem.LocMemCache"

    def test_smoke_set_get_incr(self):
        """Operaciones que usan ratelimit/throttle: set/get/incr/delete."""
        cache.set("p24-smoke", 1, timeout=30)
        assert cache.get("p24-smoke") == 1
        assert cache.incr("p24-smoke") == 2
        cache.delete("p24-smoke")
        assert cache.get("p24-smoke") is None
