"""
Fixtures globales de la nueva estructura ``backend/tests/`` (plan cero-dudas §B1).

Provee el escenario canónico de aislamiento multi-tenant — **dos empresas + dos
usuarios** — construido sobre las factories de ``tests/factories/``, además de los
autouse que neutralizan dependencias externas (rate-limit y Celery/Redis) para que
la suite corra hermética.

Mientras dura la migración por capas, ``tests_api/`` conserva su propio
``conftest.py``; este archivo es la base de todo lo que viva bajo ``tests/``.
"""

import pytest

from django.core.cache import cache

from apps.finanzas.models import MetodoPago
from tests.factories import EmpresaFactory, MonedaFactory, UsuariosFactory


# ---------------------------------------------------------------------------
# Autouse: aislar de servicios externos (espejo de tests_api/conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    """Limpia la caché de rate limiting entre tests (evita arrastre de contadores)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _celery_memory_broker(settings):
    """Fuerza Celery a broker/resultados en memoria y ejecución síncrona (eager)."""
    settings.CELERY_BROKER_URL = "memory://"
    settings.CELERY_RESULT_BACKEND = "cache+memory://"
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
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


# ---------------------------------------------------------------------------
# Escenario de dos tenants
# ---------------------------------------------------------------------------


@pytest.fixture
def moneda_usd(db):
    """USD genérica compartida (moneda base de ambas empresas)."""
    return MonedaFactory(codigo_iso="USD", nombre="Dólar Estadounidense", simbolo="$")


@pytest.fixture
def empresa_a(db, moneda_usd):
    """Empresa A — tenant principal en los tests de aislamiento."""
    return EmpresaFactory(
        nombre_legal="Empresa Alpha S.A.",
        identificador_fiscal="J-12345678-9",
        id_moneda_base=moneda_usd,
    )


@pytest.fixture
def empresa_b(db, moneda_usd):
    """Empresa B — tenant "ajeno"; sus datos nunca deben filtrarse hacia A."""
    return EmpresaFactory(
        nombre_legal="Empresa Beta C.A.",
        identificador_fiscal="J-98765432-1",
        id_moneda_base=moneda_usd,
    )


@pytest.fixture
def user_a(db, empresa_a):
    """Usuario perteneciente a Empresa A."""
    return UsuariosFactory(username="user_empresa_a", email="user_a@alpha.test", empresa=empresa_a)


@pytest.fixture
def user_b(db, empresa_b):
    """Usuario perteneciente a Empresa B."""
    return UsuariosFactory(username="user_empresa_b", email="user_b@beta.test", empresa=empresa_b)


@pytest.fixture
def metodo_efectivo(db):
    """MetodoPago genérico (sin empresa) necesario para construir Pagos."""
    return MetodoPago.objects.create(nombre_metodo="Efectivo Test", tipo_metodo="EFECTIVO")


# ---------------------------------------------------------------------------
# Clientes API autenticados
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    """Cliente DRF sin autenticar."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def client_a(user_a):
    """Cliente DRF autenticado como usuario de Empresa A."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


@pytest.fixture
def client_b(user_b):
    """Cliente DRF autenticado como usuario de Empresa B."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user_b)
    return client
