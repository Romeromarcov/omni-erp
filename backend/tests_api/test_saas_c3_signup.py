"""
Plan C — Fase C3: auto-registro (signup) de prospectos.

Verifica el endpoint público POST /api/saas/signup/:
  - crea Empresa + usuario admin + Suscripcion TRIAL 30 días, atómicamente;
  - el trial queda operativo (suscripcion_activa lo reconoce);
  - nunca otorga privilegios de proveedor (es_superusuario_omni/is_staff False);
  - valida unicidad de username y fortaleza de contraseña;
  - responde 503 si no hay planes disponibles.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core.models import Empresa
from apps.saas.models import Plan, suscripcion_activa

pytestmark = pytest.mark.django_db

User = get_user_model()

SIGNUP_URL = "/api/saas/signup/"


@pytest.fixture(autouse=True)
def _limpiar_throttle():
    """El ScopedRateThrottle guarda estado en caché; se limpia entre tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def plan_free(db):
    return Plan.objects.create(nombre="Free", nivel="FREE", precio_mensual="0.00", precio_anual="0.00")


@pytest.fixture
def plan_pro(db):
    return Plan.objects.create(nombre="Pro", nivel="PRO", precio_mensual="50.00", precio_anual="500.00")


def _payload(**overrides):
    base = {
        "empresa_nombre_legal": "Prospecto S.A.",
        "empresa_nombre_comercial": "Prospecto",
        "empresa_identificador_fiscal": "J-50505050-5",
        "empresa_email": "contacto@prospecto.com",
        "username": "nuevo_admin",
        "email": "admin@prospecto.com",
        "password": "ContraseñaSegura123",
        "first_name": "Ana",
        "last_name": "García",
    }
    base.update(overrides)
    return base


class TestSignup:
    def test_signup_crea_empresa_usuario_y_trial(self, plan_free):
        client = APIClient()
        resp = client.post(SIGNUP_URL, _payload(), format="json")
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body["estado"] == "TRIAL"
        assert body["plan"] == "Free"

        empresa = Empresa.objects.get(pk=body["empresa_id"])
        usuario = User.objects.get(pk=body["usuario_id"])
        assert usuario.empresas.filter(pk=empresa.pk).exists()
        assert usuario.check_password("ContraseñaSegura123")

        # El trial debe quedar OPERATIVO (lo reconoce el helper de negocio).
        sus = suscripcion_activa(empresa)
        assert sus is not None
        assert sus.estado == "TRIAL"
        assert sus.esta_vigente is True
        assert sus.dias_restantes >= 29

    def test_signup_no_otorga_privilegios_de_proveedor(self, plan_free):
        """Aunque el payload intente inyectar el rol, se fuerza a False."""
        client = APIClient()
        resp = client.post(
            SIGNUP_URL,
            _payload(es_superusuario_omni=True, is_staff=True),
            format="json",
        )
        assert resp.status_code == 201
        usuario = User.objects.get(pk=resp.json()["usuario_id"])
        assert usuario.es_superusuario_omni is False
        assert usuario.is_staff is False

    def test_signup_username_duplicado_rechazado(self, plan_free):
        User.objects.create_user(username="nuevo_admin", password="x")
        client = APIClient()
        resp = client.post(SIGNUP_URL, _payload(), format="json")
        assert resp.status_code == 400
        assert "username" in resp.json()

    def test_signup_password_debil_rechazado(self, plan_free):
        client = APIClient()
        resp = client.post(SIGNUP_URL, _payload(password="123"), format="json")
        assert resp.status_code == 400
        assert "password" in resp.json()

    def test_signup_sin_planes_devuelve_503(self):
        """Sin planes activos no se puede provisionar: 503, y nada se crea."""
        client = APIClient()
        resp = client.post(SIGNUP_URL, _payload(), format="json")
        assert resp.status_code == 503
        assert not Empresa.objects.filter(nombre_legal="Prospecto S.A.").exists()
        assert not User.objects.filter(username="nuevo_admin").exists()

    def test_signup_respeta_plan_nivel_solicitado(self, plan_free, plan_pro):
        client = APIClient()
        resp = client.post(SIGNUP_URL, _payload(plan_nivel="PRO"), format="json")
        assert resp.status_code == 201
        assert resp.json()["plan"] == "Pro"

    def test_signup_atomico_no_deja_empresa_huerfana(self, plan_free):
        """Si la creación del usuario falla (username duplicado), la empresa
        tampoco debe quedar creada (transacción atómica)."""
        User.objects.create_user(username="nuevo_admin", password="x")
        empresas_antes = Empresa.objects.count()
        client = APIClient()
        resp = client.post(SIGNUP_URL, _payload(), format="json")
        assert resp.status_code == 400
        assert Empresa.objects.count() == empresas_antes
