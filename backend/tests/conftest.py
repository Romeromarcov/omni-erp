"""
Fixtures globales de la suite por capas ``backend/tests/`` (plan cero-dudas §B1).

Provee el escenario canónico de aislamiento multi-tenant — **dos empresas + dos
usuarios** — construido sobre las factories de ``tests/factories/``, además de los
autouse que neutralizan dependencias externas (rate-limit y Celery/Redis) para que
la suite corra hermética.

Conftest único de la suite (CTF-014): absorbe las fixtures que vivían en
``tests_api/conftest.py`` (``rls_test_role``, ``caja_fisica_a``, ``test_user``).
"""

import pytest

from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.finanzas.models import MetodoPago
from tests.factories import EmpresaFactory, MonedaFactory, UsuariosFactory


# ---------------------------------------------------------------------------
# Roles de BD para tests de RLS
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rls_test_role(django_db_setup, django_db_blocker):
    """Rol no-superusuario para verificar el enforcement de RLS.

    Si el rol de conexión ya está sujeto a RLS (dev local, rol no-super) devuelve
    ``None`` y los tests corren tal cual. Si el rol salta RLS (p. ej. el
    superusuario ``postgres`` de CI), crea un rol ``NOSUPERUSER NOBYPASSRLS`` con
    privilegios sobre el esquema, para que los tests hagan ``SET ROLE`` y RLS se
    aplique de verdad. Devuelve el nombre del rol o ``None``.
    """
    from django.db import connection

    from apps.core import rls

    with django_db_blocker.unblock():
        if not rls.current_role_bypasses_rls():
            return None
        with connection.cursor() as cur:
            cur.execute(
                "DO $$ BEGIN "
                "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='omni_rls_test_role') THEN "
                "DROP OWNED BY omni_rls_test_role; DROP ROLE omni_rls_test_role; "
                "END IF; END $$;"
            )
            cur.execute("CREATE ROLE omni_rls_test_role NOSUPERUSER NOBYPASSRLS")
            cur.execute("GRANT USAGE ON SCHEMA public TO omni_rls_test_role")
            cur.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                "IN SCHEMA public TO omni_rls_test_role"
            )
            cur.execute(
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES "
                "IN SCHEMA public TO omni_rls_test_role"
            )
    return "omni_rls_test_role"


# ---------------------------------------------------------------------------
# Autouse: aislar de servicios externos
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
    """Fixture legacy — mantiene compatibilidad con la suite histórica."""
    User = get_user_model()
    user = User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="testuser@example.com",
        is_active=True,
    )
    user.empresas.add(empresa_a)
    return user


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
