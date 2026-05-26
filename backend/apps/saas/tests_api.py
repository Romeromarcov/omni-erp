"""
Tests de la API SaaS — M10-T5.

Cubre: PlanViewSet (permisos de escritura restringidos a superusuarios Omni).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Empresa
from apps.saas.models import Plan

pytestmark = pytest.mark.django_db

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def empresa():
    return Empresa.objects.create(
        nombre_legal="Empresa Test SaaS",
        nombre_comercial="TestSaaS",
        identificador_fiscal="J000000001",
    )


@pytest.fixture
def usuario_normal(empresa):
    """Usuario autenticado sin privilegios de superusuario Omni."""
    user = User.objects.create_user(
        username="user_normal",
        password="pass1234",
        es_superusuario_omni=False,
    )
    user.empresas.add(empresa)
    return user


@pytest.fixture
def superusuario_omni(empresa):
    """Usuario con es_superusuario_omni=True."""
    user = User.objects.create_user(
        username="super_omni",
        password="pass1234",
        es_superusuario_omni=True,
    )
    user.empresas.add(empresa)
    return user


@pytest.fixture
def plan():
    return Plan.objects.create(
        nombre="Plan Starter Test",
        nivel="STARTER",
        precio_mensual="29.99",
        precio_anual="299.99",
    )


# ---------------------------------------------------------------------------
# perform_update — solo superusuarios Omni pueden hacer PATCH
# ---------------------------------------------------------------------------

class TestPlanUpdate:
    def test_usuario_normal_no_puede_patchear_plan(self, api_client, usuario_normal, plan):
        """Un usuario regular recibe 403 al intentar PATCH sobre un plan."""
        api_client.force_authenticate(user=usuario_normal)
        url = reverse("plan-detail", kwargs={"pk": plan.pk})
        response = api_client.patch(url, {"precio_mensual": "9.99"}, format="json")
        assert response.status_code == 403, (
            f"Se esperaba 403 pero se obtuvo {response.status_code}. "
            "Cualquier usuario autenticado NO debe poder modificar planes."
        )

    def test_superusuario_omni_puede_patchear_plan(self, api_client, superusuario_omni, plan):
        """Un superusuario Omni puede hacer PATCH sobre un plan."""
        api_client.force_authenticate(user=superusuario_omni)
        url = reverse("plan-detail", kwargs={"pk": plan.pk})
        response = api_client.patch(url, {"precio_mensual": "49.99"}, format="json")
        assert response.status_code == 200, (
            f"Se esperaba 200 pero se obtuvo {response.status_code}. "
            "El superusuario Omni SÍ debe poder modificar planes."
        )
        plan.refresh_from_db()
        assert str(plan.precio_mensual) == "49.99"

    def test_usuario_no_autenticado_no_puede_patchear_plan(self, api_client, plan):
        """Un usuario anónimo recibe 401/403 al intentar PATCH."""
        url = reverse("plan-detail", kwargs={"pk": plan.pk})
        response = api_client.patch(url, {"precio_mensual": "0.00"}, format="json")
        assert response.status_code in (401, 403)

    def test_patch_no_altera_plan_cuando_se_niega(self, api_client, usuario_normal, plan):
        """El precio original no cambia si un usuario normal intenta PATCH."""
        plan.refresh_from_db()
        precio_original = plan.precio_mensual
        api_client.force_authenticate(user=usuario_normal)
        url = reverse("plan-detail", kwargs={"pk": plan.pk})
        api_client.patch(url, {"precio_mensual": "0.01"}, format="json")
        plan.refresh_from_db()
        assert plan.precio_mensual == precio_original


# ---------------------------------------------------------------------------
# perform_create y perform_destroy — regresión (ya existían, verificamos paridad)
# ---------------------------------------------------------------------------

class TestPlanCreateDestroy:
    def test_usuario_normal_no_puede_crear_plan(self, api_client, usuario_normal):
        """Un usuario regular recibe 403 al intentar POST un nuevo plan."""
        api_client.force_authenticate(user=usuario_normal)
        url = reverse("plan-list")
        data = {"nombre": "Plan Pirata", "nivel": "PRO", "precio_mensual": "1.00"}
        response = api_client.post(url, data, format="json")
        assert response.status_code == 403

    def test_usuario_normal_no_puede_eliminar_plan(self, api_client, usuario_normal, plan):
        """Un usuario regular recibe 403 al intentar DELETE un plan."""
        api_client.force_authenticate(user=usuario_normal)
        url = reverse("plan-detail", kwargs={"pk": plan.pk})
        response = api_client.delete(url)
        assert response.status_code == 403
