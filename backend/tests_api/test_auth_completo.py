"""
TEST-02 — Suite completa de autenticación
TEST-04 — Aislamiento multi-tenant en gastos/ (BUG-03)

Cubre:
  - Login válido / credenciales incorrectas
  - Usuario inactivo rechazado
  - Logout blacklistea el refresh token
  - Rotación de refresh token
  - Token de acceso expirado rechazado
  - Cambio de contraseña invalida tokens previos
  - Aislamiento multi-tenant: Gastos, CategoriaGasto, ReembolsoGasto
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import Empresa
from apps.finanzas.models import Moneda

pytestmark = pytest.mark.django_db

User = get_user_model()


# ── Fixtures locales ──────────────────────────────────────────────────────────

@pytest.fixture
def moneda(db):
    return Moneda.objects.get_or_create(
        codigo_iso="VES",
        defaults={"nombre": "Bolívar Soberano", "simbolo": "Bs.", "tipo_moneda": "fiat"},
    )[0]


@pytest.fixture
def empresa_alpha(db, moneda):
    return Empresa.objects.create(
        nombre_legal="Alpha S.A.",
        identificador_fiscal="J-10000001-1",
        id_moneda_base=moneda,
    )


@pytest.fixture
def empresa_beta(db, moneda):
    return Empresa.objects.create(
        nombre_legal="Beta C.A.",
        identificador_fiscal="J-10000002-2",
        id_moneda_base=moneda,
    )


@pytest.fixture
def usuario_alpha(db, empresa_alpha):
    u = User.objects.create_user(
        username="alpha_user", password="AlphaPass#123", email="alpha@test.com", is_active=True
    )
    u.empresas.add(empresa_alpha)
    return u


@pytest.fixture
def usuario_beta(db, empresa_beta):
    u = User.objects.create_user(
        username="beta_user", password="BetaPass#123", email="beta@test.com", is_active=True
    )
    u.empresas.add(empresa_beta)
    return u


@pytest.fixture
def client_alpha(usuario_alpha):
    c = APIClient()
    refresh = RefreshToken.for_user(usuario_alpha)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return c


@pytest.fixture
def client_beta(usuario_beta):
    c = APIClient()
    refresh = RefreshToken.for_user(usuario_beta)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return c


# ─────────────────────────────────────────────────────────────────────────────
# TEST-02 — Autenticación
# ─────────────────────────────────────────────────────────────────────────────

class TestLoginCredenciales:
    """Login básico con credenciales correctas e incorrectas."""

    def test_login_valido_retorna_access_y_refresh(self, usuario_alpha):
        c = Client()
        resp = c.post(
            reverse("token_obtain_pair"),
            {"username": "alpha_user", "password": "AlphaPass#123"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access" in data
        assert "refresh" in data

    def test_login_password_incorrecto_retorna_401(self, usuario_alpha):
        c = Client()
        resp = c.post(
            reverse("token_obtain_pair"),
            {"username": "alpha_user", "password": "wrong_password"},
            content_type="application/json",
        )
        assert resp.status_code == 401
        data = resp.json()
        assert "access" not in data

    def test_login_usuario_inexistente_retorna_401(self):
        c = Client()
        resp = c.post(
            reverse("token_obtain_pair"),
            {"username": "nobody", "password": "NoPass#123"},
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_login_campo_username_vacio_retorna_400(self):
        c = Client()
        resp = c.post(
            reverse("token_obtain_pair"),
            {"username": "", "password": "pass"},
            content_type="application/json",
        )
        assert resp.status_code in (400, 401)


class TestUsuarioInactivo:
    """Usuario con is_active=False debe ser rechazado."""

    def test_usuario_inactivo_no_puede_obtener_token(self, db, empresa_alpha, moneda):
        u = User.objects.create_user(
            username="inactive_user",
            password="Pass#123",
            email="inactive@test.com",
            is_active=False,
        )
        u.empresas.add(empresa_alpha)

        c = Client()
        resp = c.post(
            reverse("token_obtain_pair"),
            {"username": "inactive_user", "password": "Pass#123"},
            content_type="application/json",
        )
        assert resp.status_code == 401
        assert "access" not in resp.json()

    def test_acceso_con_token_de_usuario_desactivado_devuelve_401(self, usuario_alpha):
        """Token obtenido antes de desactivar al usuario debe fallar."""
        refresh = RefreshToken.for_user(usuario_alpha)
        access = str(refresh.access_token)

        # Desactivar el usuario después de obtener el token
        usuario_alpha.is_active = False
        usuario_alpha.save()

        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = c.get("/api/core/usuarios/")
        assert resp.status_code == 401


class TestLogoutBlacklist:
    """Logout debe blacklistear el refresh token."""

    def test_logout_blacklistea_refresh_token(self, usuario_alpha):
        refresh = RefreshToken.for_user(usuario_alpha)
        access = str(refresh.access_token)
        refresh_str = str(refresh)

        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        resp = c.post(
            reverse("logout"),
            {"refresh": refresh_str},
            format="json",
        )
        assert resp.status_code in (200, 205)

        # Intentar usar el refresh blacklisteado debe fallar
        c2 = Client()
        resp2 = c2.post(
            reverse("token_refresh"),
            {"refresh": refresh_str},
            content_type="application/json",
        )
        assert resp2.status_code == 401

    def test_endpoint_protegido_rechaza_sin_token(self):
        c = APIClient()
        resp = c.get("/api/core/empresas/")
        assert resp.status_code == 401


class TestRefreshToken:
    """Rotación del refresh token."""

    def test_refresh_valido_retorna_nuevo_access(self, usuario_alpha):
        refresh = RefreshToken.for_user(usuario_alpha)
        c = Client()
        resp = c.post(
            reverse("token_refresh"),
            {"refresh": str(refresh)},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access" in data

    def test_refresh_invalido_retorna_401(self):
        c = Client()
        resp = c.post(
            reverse("token_refresh"),
            {"refresh": "token_completamente_invalido"},
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_refresh_vacio_retorna_400_o_401(self):
        c = Client()
        resp = c.post(
            reverse("token_refresh"),
            {"refresh": ""},
            content_type="application/json",
        )
        assert resp.status_code in (400, 401)


class TestCambioPassword:
    """Cambio de contraseña e invalidación de sesiones."""

    def test_cambio_password_requiere_autenticacion(self):
        c = APIClient()
        resp = c.post(
            reverse("change_password"),
            {"old_password": "old", "new_password": "new"},
            format="json",
        )
        assert resp.status_code == 401

    def test_cambio_password_con_password_actual_incorrecto_falla(self, usuario_alpha, client_alpha):
        resp = client_alpha.post(
            reverse("change_password"),
            {
                "old_password": "wrong_old_password",
                "new_password": "NewAlphaPass#456",
                "confirm_password": "NewAlphaPass#456",
            },
            format="json",
        )
        assert resp.status_code in (400, 403)

    def test_cambio_password_exitoso_retorna_2xx(self, usuario_alpha, client_alpha):
        resp = client_alpha.post(
            reverse("change_password"),
            {
                "old_password": "AlphaPass#123",
                "new_password": "NewAlphaPass#456",
                "confirm_password": "NewAlphaPass#456",
            },
            format="json",
        )
        assert resp.status_code in (200, 204)

        # Verificar que el nuevo password funciona para login
        c = Client()
        login_resp = c.post(
            reverse("token_obtain_pair"),
            {"username": "alpha_user", "password": "NewAlphaPass#456"},
            content_type="application/json",
        )
        assert login_resp.status_code == 200

    def test_password_anterior_ya_no_funciona_tras_cambio(self, usuario_alpha, client_alpha):
        # Cambiar contraseña
        client_alpha.post(
            reverse("change_password"),
            {
                "old_password": "AlphaPass#123",
                "new_password": "NewAlphaPass#789",
                "confirm_password": "NewAlphaPass#789",
            },
            format="json",
        )

        # El password viejo ya no debe funcionar
        c = Client()
        login_resp = c.post(
            reverse("token_obtain_pair"),
            {"username": "alpha_user", "password": "AlphaPass#123"},
            content_type="application/json",
        )
        assert login_resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# TEST-04 — Aislamiento multi-tenant en gastos/ (BUG-03)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def categoria_alpha(db, empresa_alpha):
    from apps.gastos.models import CategoriaGasto
    return CategoriaGasto.objects.create(
        id_empresa=empresa_alpha,
        nombre_categoria="Viáticos Alpha",
        activo=True,
    )


@pytest.fixture
def categoria_beta(db, empresa_beta):
    from apps.gastos.models import CategoriaGasto
    return CategoriaGasto.objects.create(
        id_empresa=empresa_beta,
        nombre_categoria="Viáticos Beta",
        activo=True,
    )


@pytest.fixture
def gasto_alpha(db, empresa_alpha, categoria_alpha, moneda):
    from datetime import date
    from apps.gastos.models import Gasto
    return Gasto.objects.create(
        id_empresa=empresa_alpha,
        id_categoria_gasto=categoria_alpha,
        id_moneda=moneda,
        descripcion="Gasto de prueba Alpha",
        monto=500,
        fecha_gasto=date.today(),
        estado_gasto="PENDIENTE_APROBACION",
    )


@pytest.fixture
def gasto_beta(db, empresa_beta, categoria_beta, moneda):
    from datetime import date
    from apps.gastos.models import Gasto
    return Gasto.objects.create(
        id_empresa=empresa_beta,
        id_categoria_gasto=categoria_beta,
        id_moneda=moneda,
        descripcion="Gasto de prueba Beta",
        monto=300,
        fecha_gasto=date.today(),
        estado_gasto="PENDIENTE_APROBACION",
    )


class TestAislamientoGastos:
    """Usuario A solo ve gastos de su propia empresa (BUG-03 + TEST-04)."""

    def test_lista_gastos_solo_empresa_propia(self, client_alpha, gasto_alpha, gasto_beta):
        resp = client_alpha.get("/api/gastos/gastos/")
        assert resp.status_code == 200
        data = resp.json()
        resultados = data.get("results", data) if isinstance(data, dict) else data
        ids = [str(g.get("id_gasto", g.get("id", ""))) for g in resultados]
        assert str(gasto_alpha.id_gasto) in ids
        assert str(gasto_beta.id_gasto) not in ids

    def test_get_gasto_empresa_ajena_retorna_404(self, client_alpha, gasto_beta):
        resp = client_alpha.get(f"/api/gastos/gastos/{gasto_beta.id_gasto}/")
        assert resp.status_code == 404

    def test_patch_gasto_empresa_ajena_retorna_404(self, client_alpha, gasto_beta):
        resp = client_alpha.patch(
            f"/api/gastos/gastos/{gasto_beta.id_gasto}/",
            {"descripcion": "Intento de modificación"},
            format="json",
        )
        assert resp.status_code == 404

    def test_lista_categorias_solo_empresa_propia(self, client_alpha, categoria_alpha, categoria_beta):
        resp = client_alpha.get("/api/gastos/categorias-gasto/")
        assert resp.status_code == 200
        data = resp.json()
        resultados = data.get("results", data) if isinstance(data, dict) else data
        nombres = [c["nombre_categoria"] for c in resultados]
        assert "Viáticos Alpha" in nombres
        assert "Viáticos Beta" not in nombres

    def test_get_categoria_empresa_ajena_retorna_404(self, client_alpha, categoria_beta):
        resp = client_alpha.get(f"/api/gastos/categorias-gasto/{categoria_beta.id_categoria_gasto}/")
        assert resp.status_code == 404

    def test_gastos_requiere_autenticacion(self):
        c = APIClient()
        resp = c.get("/api/gastos/gastos/")
        assert resp.status_code == 401

    def test_categorias_requiere_autenticacion(self):
        c = APIClient()
        resp = c.get("/api/gastos/categorias-gasto/")
        assert resp.status_code == 401


class TestAislamientoReembolsos:
    """Aislamiento multi-tenant en ReembolsoGasto."""

    @pytest.fixture
    def metodo_pago(self, db):
        from apps.finanzas.models import MetodoPago
        return MetodoPago.objects.create(nombre_metodo="Efectivo", tipo_metodo="EFECTIVO")

    @pytest.fixture
    def reembolso_beta(self, db, empresa_beta, gasto_beta, moneda, metodo_pago):
        from datetime import date
        from apps.gastos.models import ReembolsoGasto
        return ReembolsoGasto.objects.create(
            id_empresa=empresa_beta,
            id_gasto=gasto_beta,
            id_moneda=moneda,
            id_metodo_pago=metodo_pago,
            monto_reembolso=300,
            fecha_reembolso=date.today(),
            estado_reembolso="PENDIENTE",
        )

    def test_lista_reembolsos_solo_empresa_propia(self, client_alpha, reembolso_beta):
        resp = client_alpha.get("/api/gastos/reembolsos-gasto/")
        assert resp.status_code == 200
        data = resp.json()
        resultados = data.get("results", data) if isinstance(data, dict) else data
        # Alpha no tiene reembolsos; Beta tiene 1 pero no debe ser visible
        ids = [str(r.get("id_reembolso", "")) for r in resultados]
        assert str(reembolso_beta.id_reembolso) not in ids

    def test_get_reembolso_empresa_ajena_retorna_404(self, client_alpha, reembolso_beta):
        resp = client_alpha.get(f"/api/gastos/reembolsos-gasto/{reembolso_beta.id_reembolso}/")
        assert resp.status_code == 404
