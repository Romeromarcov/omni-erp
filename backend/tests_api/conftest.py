import pytest

from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.core.models import Empresa
from apps.finanzas.models import Moneda  # Moneda está en finanzas, no en core


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    """
    Limpia la caché de rate limiting (LocMemCache) antes de cada test.
    Previene que los contadores de intentos se acumulen entre tests (SEC-07).
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _celery_memory_broker(settings):
    """
    Override Celery broker to in-memory for all tests.
    Prevents Kombu from importing the Redis transport (which may not be installed).
    Also enables eager execution so tasks run synchronously.
    """
    settings.CELERY_BROKER_URL = "memory://"
    settings.CELERY_RESULT_BACKEND = "cache+memory://"
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    # Reconfigure the already-loaded Celery app
    try:
        from config.celery import app as celery_app
        celery_app.conf.update(
            broker_url="memory://",
            result_backend="cache+memory://",
            task_always_eager=True,
            task_eager_propagates=True,
        )
    except Exception:
        pass


@pytest.fixture
def moneda_usd(db):
    """Moneda USD compartida para tests que necesiten una moneda base."""
    return Moneda.objects.create(
        nombre="Dólar Estadounidense",
        codigo_iso="USD",
        simbolo="$",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def empresa_a(db, moneda_usd):
    """Empresa A para tests de aislamiento multi-tenant."""
    return Empresa.objects.create(
        nombre_legal="Empresa Alpha S.A.",
        identificador_fiscal="J-12345678-9",
        id_moneda_base=moneda_usd,
    )


@pytest.fixture
def empresa_b(db, moneda_usd):
    """Empresa B para tests de aislamiento multi-tenant."""
    return Empresa.objects.create(
        nombre_legal="Empresa Beta C.A.",
        identificador_fiscal="J-98765432-1",
        id_moneda_base=moneda_usd,
    )


@pytest.fixture
def user_a(db, empresa_a):
    """Usuario perteneciente a Empresa A."""
    User = get_user_model()
    user = User.objects.create_user(
        username="user_empresa_a",
        password="testpass123",
        email="user_a@empresaalpha.com",
        is_active=True,
    )
    user.empresas.add(empresa_a)
    return user


@pytest.fixture
def user_b(db, empresa_b):
    """Usuario perteneciente a Empresa B."""
    User = get_user_model()
    user = User.objects.create_user(
        username="user_empresa_b",
        password="testpass123",
        email="user_b@empresabeta.com",
        is_active=True,
    )
    user.empresas.add(empresa_b)
    return user


@pytest.fixture
def caja_fisica_a(db, empresa_a):
    """CajaFisica para Empresa A — usada en tests de sesión de caja."""
    from apps.finanzas.models import CajaFisica

    return CajaFisica.objects.create(
        empresa=empresa_a,
        nombre="Caja Principal Test",
        identificador_dispositivo="test-device-001",
    )


@pytest.fixture
def test_user(db, empresa_a, moneda_usd):
    """Fixture legacy — mantiene compatibilidad con código anterior."""
    User = get_user_model()
    user = User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="testuser@example.com",
        is_active=True,
    )
    user.empresas.add(empresa_a)
    return user
