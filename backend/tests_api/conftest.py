import pytest
from django.contrib.auth import get_user_model
from apps.core.models import Empresa, Moneda

@pytest.fixture
def test_user(db):
    # Crea una moneda y empresa requeridas por el modelo multi-tenant
    moneda = Moneda.objects.create(
        nombre="Dólar",
        codigo_iso="USD",
        simbolo="$",
        tipo_moneda="fiat",
        es_generica=True  # O ajusta según necesidad
    )
    empresa = Empresa.objects.create(
        nombre_legal="Empresa Test",
        identificador_fiscal="J123456789",
        id_moneda_base=moneda
    )
    User = get_user_model()
    user = User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="testuser@example.com",
        is_active=True
    )
    user.empresas.add(empresa)
    return user
