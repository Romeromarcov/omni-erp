import pytest
from django.contrib.auth import get_user_model
from apps.core.models import Empresa
from apps.finanzas.models import Moneda  # Moneda está en finanzas, no en core


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
