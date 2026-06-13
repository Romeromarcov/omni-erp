"""
Plan C — Fase C2: control de acceso por pago (extremo a extremo).

Complementa a tests/integration/test_saas_middleware.py (que usa RequestFactory y mocks)
con dos cosas que solo se ven de punta a punta:

  1. Resolución de usuario vía Bearer JWT en el middleware. En producción la SPA
     se autentica con JWT y, a nivel de middleware Django, `request.user` es
     AnonymousUser; el middleware debe resolver el usuario del token igualmente.
  2. Bypass del superusuario Omni (el proveedor no requiere suscripción).

Además cubre la authz de SuscripcionViewSet: solo el proveedor puede crear /
suspender / cancelar suscripciones (un tenant no debe auto-gestionar su billing).
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.saas.models import Plan, Suscripcion

pytestmark = pytest.mark.django_db

User = get_user_model()

# Ruta autenticada y NO excluida; el middleware se evalúa antes que la vista.
RUTA_PROTEGIDA = "/api/core/empresas/"


@pytest.fixture
def plan_c2(db):
    return Plan.objects.create(
        nombre="Plan C2", nivel="PRO", precio_mensual="10.00", precio_anual="100.00",
    )


@pytest.fixture
def superusuario_omni(db, empresa_a):
    user = User.objects.create_user(
        username="omni_c2", password="pass1234", es_superusuario_omni=True,
    )
    user.empresas.add(empresa_a)
    return user


def _auth_jwt(client: APIClient, user) -> None:
    """Bearer JWT real (no force_authenticate) para ejercitar el middleware."""
    token = str(AccessToken.for_user(user))
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


def _suscripcion_activa(empresa, plan):
    hoy = timezone.now().date()
    return Suscripcion.objects.create(
        id_empresa=empresa,
        id_plan=plan,
        estado="ACTIVA",
        fecha_inicio=hoy - timedelta(days=1),
        fecha_fin=hoy + timedelta(days=30),
    )


@pytest.fixture
def verificacion_activa(settings):
    """Activa el control de acceso por pago para el test (fixture pytest-django)."""
    settings.SAAS_VERIFICAR_SUSCRIPCION = True
    return settings


class TestMiddleware402ConJWT:
    def test_sin_suscripcion_devuelve_402(self, verificacion_activa, empresa_a, user_a):
        client = APIClient()
        _auth_jwt(client, user_a)
        resp = client.get(RUTA_PROTEGIDA)
        assert resp.status_code == 402
        assert resp.json().get("codigo") == "SUSCRIPCION_REQUERIDA"

    def test_con_suscripcion_activa_pasa(self, verificacion_activa, empresa_a, plan_c2, user_a):
        _suscripcion_activa(empresa_a, plan_c2)
        client = APIClient()
        _auth_jwt(client, user_a)
        resp = client.get(RUTA_PROTEGIDA)
        assert resp.status_code == 200

    def test_superusuario_omni_no_requiere_suscripcion(self, verificacion_activa, empresa_a, superusuario_omni):
        client = APIClient()
        _auth_jwt(client, superusuario_omni)
        resp = client.get(RUTA_PROTEGIDA)
        assert resp.status_code == 200

    def test_ruta_saas_excluida_no_bloquea(self, verificacion_activa, empresa_a, user_a):
        """El propio panel SaaS (/api/saas/) nunca se bloquea: si no, un tenant
        sin plan no podría ni consultar su estado de suscripción."""
        client = APIClient()
        _auth_jwt(client, user_a)
        resp = client.get("/api/saas/planes/")
        assert resp.status_code == 200

    def test_anonimo_no_recibe_402(self, verificacion_activa):
        """Sin token, la vista responde 401 — el middleware no lo enmascara."""
        client = APIClient()
        resp = client.get(RUTA_PROTEGIDA)
        assert resp.status_code == 401


class TestSuscripcionAuthz:
    """Escritura de suscripciones restringida al proveedor (es_superusuario_omni)."""

    def _payload(self, empresa, plan):
        hoy = timezone.now().date()
        return {
            "id_empresa": str(empresa.pk),
            "id_plan": str(plan.pk),
            "estado": "ACTIVA",
            "periodo": "MENSUAL",
            "fecha_inicio": hoy.isoformat(),
            "fecha_fin": (hoy + timedelta(days=30)).isoformat(),
        }

    def test_tenant_no_puede_crear_suscripcion(self, empresa_a, plan_c2, user_a):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(reverse("suscripcion-list"), self._payload(empresa_a, plan_c2), format="json")
        assert resp.status_code == 403

    def test_proveedor_puede_crear_suscripcion(self, empresa_a, plan_c2, superusuario_omni):
        client = APIClient()
        client.force_authenticate(user=superusuario_omni)
        resp = client.post(reverse("suscripcion-list"), self._payload(empresa_a, plan_c2), format="json")
        assert resp.status_code == 201

    def test_tenant_puede_suspender_la_suya(self, empresa_a, plan_c2, user_a):
        """Self-service: el tenant suspende su propia suscripción (200)."""
        sus = _suscripcion_activa(empresa_a, plan_c2)
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(reverse("suscripcion-suspender", kwargs={"pk": sus.pk}), {}, format="json")
        assert resp.status_code == 200
        sus.refresh_from_db()
        assert sus.estado == "SUSPENDIDA"

    def test_tenant_puede_cancelar_la_suya(self, empresa_a, plan_c2, user_a):
        """Self-service churn: el tenant cancela su propia suscripción (200)."""
        sus = _suscripcion_activa(empresa_a, plan_c2)
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(reverse("suscripcion-cancelar", kwargs={"pk": sus.pk}), {}, format="json")
        assert resp.status_code == 200
        sus.refresh_from_db()
        assert sus.estado == "CANCELADA"

    def test_tenant_no_puede_reactivar(self, empresa_a, plan_c2, user_a):
        """La reactivación (PATCH estado=ACTIVA) es solo del proveedor: un tenant
        no puede revertir una suspensión que le impusieron."""
        sus = _suscripcion_activa(empresa_a, plan_c2)
        sus.suspender()
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.patch(
            reverse("suscripcion-detail", kwargs={"pk": sus.pk}),
            {"estado": "ACTIVA"}, format="json",
        )
        assert resp.status_code == 403
        sus.refresh_from_db()
        assert sus.estado == "SUSPENDIDA"

    def test_proveedor_puede_suspender(self, empresa_a, plan_c2, superusuario_omni):
        sus = _suscripcion_activa(empresa_a, plan_c2)
        client = APIClient()
        client.force_authenticate(user=superusuario_omni)
        resp = client.post(reverse("suscripcion-suspender", kwargs={"pk": sus.pk}), {}, format="json")
        assert resp.status_code == 200
        sus.refresh_from_db()
        assert sus.estado == "SUSPENDIDA"

    def test_tenant_puede_leer_suscripciones(self, empresa_a, plan_c2, user_a):
        """La LECTURA sigue abierta y acotada por tenant (no se restringe)."""
        _suscripcion_activa(empresa_a, plan_c2)
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get(reverse("suscripcion-list"))
        assert resp.status_code == 200
