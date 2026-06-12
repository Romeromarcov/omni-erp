"""
Backfill de cobertura — flujo de DISPOSITIVOS en apps/core/auth_views.py.

Complementa ``test_auth_completo.py`` y ``test_auth_views_cobertura.py`` (que cubren
el login SIN device_fingerprint, profile, refresh, etc.) ejercitando las ramas que
quedaban sin cubrir:

- ``login_view`` CON ``device_fingerprint``:
  * usuario sin sucursal → login OK sin bloque "dispositivo" (rama empresa/sucursal faltante)
  * usuario normal, dispositivo nuevo → accion "nada" (sin permisos para crear caja;
    se marca preguntar_crear_caja=False)
  * dispositivo con preguntar_crear_caja=False → accion "nada" (rama temprana)
  * superusuario omni, dispositivo nuevo → accion "preguntar_caja" con datos de
    empresa/sucursal/user_agent/ip
  * dispositivo con caja física SIN sesión activa → "abrir_sesion_automatico" + sesión abierta
  * dispositivo con caja física CON sesión activa → "sesion_activa" + datos serializados
  * error interno en la detección → dispositivo_info = {"error": ...} sin romper el login
  * error al abrir la sesión automática → "error_sesion" en la respuesta

- ``dispositivo_accion_view`` (/api/core/dispositivos/accion/):
  * validaciones 400/404 (parámetros faltantes, dispositivo ajeno/inexistente)
  * crear_caja_fisica: 400 sin nombre, 403 sin permisos, 201 feliz (caja +
    CajaFisicaUsuario + asociación + sesión), 500 con error interno
  * no_preguntar_caja: 200 y flag persistido
  * abrir_sesion: 400 sin caja, 200 feliz, 500 con error interno
  * acción desconocida → 400

Fixtures empresa_a / user_a / moneda_usd vienen del conftest de tests/.
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.core.models import Dispositivo, Sucursal
from apps.finanzas.models import CajaFisica, CajaFisicaUsuario, SesionCajaFisica

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
ACCION_URL = "/api/core/dispositivos/accion/"
PASSWORD = "testpass123"
FP = "fp-test-dispositivo-001"
UA_WIN_CHROME = "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"


@pytest.fixture
def sucursal_a(empresa_a):
    return Sucursal.objects.create(
        id_empresa=empresa_a,
        nombre="Sucursal Central",
        codigo_sucursal="SUC-A1",
    )


@pytest.fixture
def user_con_sucursal(user_a, sucursal_a):
    user_a.sucursales.add(sucursal_a)
    return user_a


@pytest.fixture
def superuser_con_sucursal(user_con_sucursal):
    user_con_sucursal.es_superusuario_omni = True
    user_con_sucursal.save(update_fields=["es_superusuario_omni"])
    return user_con_sucursal


def _login(user, **extra):
    payload = {"username": user.username, "password": PASSWORD, "device_fingerprint": FP}
    payload.update(extra)
    return APIClient().post(LOGIN_URL, payload, format="json")


@pytest.fixture
def dispositivo_a(empresa_a, sucursal_a, user_con_sucursal):
    return Dispositivo.objects.create(
        fingerprint=FP,
        user_agent=UA_WIN_CHROME,
        ip_address="10.0.0.1",
        nombre_dispositivo="Chrome en Windows",
        empresa=empresa_a,
        sucursal=sucursal_a,
        creado_por=user_con_sucursal,
    )


@pytest.fixture
def caja_a(empresa_a, sucursal_a):
    return CajaFisica.objects.create(
        empresa=empresa_a,
        sucursal=sucursal_a,
        nombre="Caja Dispositivo",
        identificador_dispositivo="disp-caja-001",
    )


# ── login_view con device_fingerprint ─────────────────────────────────────────


class TestLoginConDispositivo:
    def test_usuario_sin_sucursal_login_ok_sin_dispositivo(self, user_a):
        """Sin sucursal asignada no se procesa el dispositivo (rama de warning)."""
        resp = _login(user_a)
        assert resp.status_code == 200
        assert "dispositivo" not in resp.json()
        assert Dispositivo.objects.count() == 0

    def test_usuario_normal_dispositivo_nuevo_accion_nada(self, user_con_sucursal):
        """Usuario sin permisos de crear caja: el dispositivo se registra,
        se marca no-preguntar y la acción es 'nada'."""
        resp = _login(user_con_sucursal, device_user_agent=UA_WIN_CHROME, device_ip="10.1.1.1")
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["creado"] is True
        assert info["accion"] == "nada"
        assert info["datos"] == {}
        disp = Dispositivo.objects.get(fingerprint=FP)
        assert disp.nombre_dispositivo == "Chrome en Windows"
        assert disp.preguntar_crear_caja is False  # marcado por determinar_accion
        assert disp.ultima_pregunta_caja is not None

    def test_dispositivo_existente_no_preguntar_accion_nada(self, user_con_sucursal, dispositivo_a):
        dispositivo_a.preguntar_crear_caja = False
        dispositivo_a.save(update_fields=["preguntar_crear_caja"])
        resp = _login(user_con_sucursal)
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["creado"] is False
        assert info["accion"] == "nada"
        assert info["mensaje"] == "Dispositivo registrado sin caja física asociada"

    def test_superusuario_dispositivo_nuevo_preguntar_caja(self, superuser_con_sucursal, empresa_a, sucursal_a):
        resp = _login(superuser_con_sucursal, device_user_agent=UA_WIN_CHROME, device_ip="10.2.2.2")
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["accion"] == "preguntar_caja"
        datos = info["datos"]
        assert datos["empresa"]["id_empresa"] == str(empresa_a.id_empresa)
        assert datos["sucursal"]["id_sucursal"] == str(sucursal_a.id_sucursal)
        assert datos["sucursal"]["nombre"] == "Sucursal Central"
        assert datos["user_agent"] == UA_WIN_CHROME
        assert datos["ip_address"] == "10.2.2.2"
        assert datos["dispositivo"]["fingerprint"] == FP

    def test_dispositivo_con_caja_sin_sesion_abre_automatico(
        self, user_con_sucursal, dispositivo_a, caja_a
    ):
        dispositivo_a.caja_fisica = caja_a
        dispositivo_a.save()
        resp = _login(user_con_sucursal, device_ip="10.3.3.3")
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["accion"] == "abrir_sesion_automatico"
        assert info["datos"]["caja_fisica"]["nombre"] == "Caja Dispositivo"
        sesion_info = info["sesion_abierta"]
        assert sesion_info["estado"] == "ABIERTA"
        assert sesion_info["caja_fisica"]["id_caja_fisica"] == str(caja_a.id_caja_fisica)
        sesion = SesionCajaFisica.objects.get(id_sesion=sesion_info["id_sesion"])
        assert sesion.usuario == user_con_sucursal
        assert sesion.estado == "ABIERTA"
        assert sesion.ip_address == "10.3.3.3"

    def test_dispositivo_con_sesion_activa_no_abre_otra(
        self, user_con_sucursal, dispositivo_a, caja_a
    ):
        dispositivo_a.caja_fisica = caja_a
        dispositivo_a.save()
        sesion = SesionCajaFisica.abrir_sesion(caja_fisica=caja_a, usuario=user_con_sucursal)
        resp = _login(user_con_sucursal)
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["accion"] == "sesion_activa"
        assert info["datos"]["sesion"]["id_sesion"] == str(sesion.id_sesion)
        assert info["datos"]["caja_fisica"]["id_caja_fisica"] == str(caja_a.id_caja_fisica)
        assert "sesion_abierta" not in info
        # Sigue habiendo UNA sola sesión abierta
        assert SesionCajaFisica.objects.filter(caja_fisica=caja_a, estado="ABIERTA").count() == 1

    def test_error_en_deteccion_devuelve_error_interno_sin_romper_login(self, user_con_sucursal):
        with patch(
            "apps.core.utils.detectar_o_registrar_dispositivo",
            side_effect=RuntimeError("boom"),
        ):
            resp = _login(user_con_sucursal)
        assert resp.status_code == 200  # el login NO falla
        assert resp.json()["dispositivo"] == {"error": "Error interno al procesar el dispositivo."}
        assert "access" in resp.json()

    def test_error_abriendo_sesion_automatica_reporta_error_sesion(
        self, user_con_sucursal, dispositivo_a, caja_a
    ):
        dispositivo_a.caja_fisica = caja_a
        dispositivo_a.save()
        with patch(
            "apps.finanzas.models.SesionCajaFisica.abrir_sesion",
            side_effect=RuntimeError("db down"),
        ):
            resp = _login(user_con_sucursal)
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["accion"] == "abrir_sesion_automatico"
        assert info["error_sesion"] == "No se pudo abrir la sesión automáticamente."
        assert "sesion_abierta" not in info


class TestLoginAccionAbrirSesionModal:
    """Rama ``accion == "abrir_sesion"`` (modal) de login_view.

    NOTA: ``determinar_accion_dispositivo`` actual nunca retorna "abrir_sesion"
    (solo nada/preguntar_caja/abrir_sesion_automatico/sesion_activa), así que esta
    rama solo es alcanzable mockeando la decisión — se cubre igual porque el
    contrato del view la soporta explícitamente.
    """

    def test_accion_abrir_sesion_modal_abre_sesion(self, user_con_sucursal, dispositivo_a, caja_a):
        accion = {
            "accion": "abrir_sesion",
            "mensaje": "Abrir sesión",
            "datos": {"caja_fisica": caja_a},
        }
        with patch("apps.core.utils.determinar_accion_dispositivo", return_value=accion):
            resp = _login(user_con_sucursal, device_ip="10.4.4.4")
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["accion"] == "abrir_sesion"
        assert info["datos"]["caja_fisica"]["id_caja_fisica"] == str(caja_a.id_caja_fisica)
        sesion = SesionCajaFisica.objects.get(id_sesion=info["sesion_abierta"]["id_sesion"])
        assert sesion.estado == "ABIERTA"
        assert sesion.ip_address == "10.4.4.4"

    def test_accion_abrir_sesion_modal_con_error_reporta_error_sesion(
        self, user_con_sucursal, dispositivo_a, caja_a
    ):
        accion = {
            "accion": "abrir_sesion",
            "mensaje": "Abrir sesión",
            "datos": {"caja_fisica": caja_a},
        }
        with patch("apps.core.utils.determinar_accion_dispositivo", return_value=accion), patch(
            "apps.finanzas.models.SesionCajaFisica.abrir_sesion",
            side_effect=RuntimeError("falla"),
        ):
            resp = _login(user_con_sucursal)
        assert resp.status_code == 200
        info = resp.json()["dispositivo"]
        assert info["error_sesion"] == "No se pudo abrir la sesión automáticamente."


class TestUrefYTokenObtain:
    """Ramas restantes de auth_views: _uref vacío y rate-limit/log del token endpoint."""

    def test_uref_username_vacio(self):
        from apps.core.auth_views import _uref

        assert _uref("") == "user=<vacío>"
        assert _uref(None) == "user=<vacío>"
        # No reversible: nunca contiene el username en claro
        assert "marco" not in _uref("marco")
        assert _uref("marco").startswith("user#")

    def test_token_obtain_credenciales_invalidas_401(self, user_con_sucursal):
        resp = APIClient().post(
            "/api/auth/token/",
            {"username": user_con_sucursal.username, "password": "mala"},
            format="json",
        )
        assert resp.status_code == 401

    def test_token_obtain_rate_limit_429(self, user_con_sucursal):
        """SEC-07: >5 POST/min por IP al token endpoint → 429."""
        from unittest import mock

        from django_ratelimit import core as ratelimit_core

        client = APIClient()
        # django-ratelimit cuenta en buckets alineados al minuto epoch: si las
        # 7 peticiones cruzan un borde de minuto, ningún bucket supera 5 y el
        # test flaquea (visto en CI: 7×401 sin 429). Congelar el reloj DEL
        # módulo ratelimit (no el global) garantiza una sola ventana.
        with mock.patch.object(ratelimit_core, "time") as reloj:
            reloj.time.return_value = 1_900_000_000.0
            codigos = [
                client.post(
                    "/api/auth/token/",
                    {"username": user_con_sucursal.username, "password": "x"},
                    format="json",
                ).status_code
                for _ in range(7)
            ]
        assert 429 in codigos


class TestLogoutYChangePasswordRamas:
    """Ramas de error de logout_view y change_password_view sin cubrir."""

    def test_logout_con_refresh_invalido_400(self, user_con_sucursal):
        client = APIClient()
        client.force_authenticate(user=user_con_sucursal)
        resp = client.post("/api/auth/logout/", {"refresh": "no-es-un-jwt"}, format="json")
        assert resp.status_code == 400
        assert resp.json()["error"] == "Error during logout"

    def test_change_password_faltan_campos_400(self, user_con_sucursal):
        client = APIClient()
        client.force_authenticate(user=user_con_sucursal)
        resp = client.post("/api/auth/change-password/", {"old_password": PASSWORD}, format="json")
        assert resp.status_code == 400
        assert resp.json()["error"] == "Both old and new passwords are required"

    def test_change_password_nueva_invalida_400(self, user_con_sucursal):
        """validate_password rechaza passwords demasiado cortas/comunes."""
        client = APIClient()
        client.force_authenticate(user=user_con_sucursal)
        resp = client.post(
            "/api/auth/change-password/",
            {"old_password": PASSWORD, "new_password": "123"},
            format="json",
        )
        assert resp.status_code == 400
        assert isinstance(resp.json()["error"], list)

    def test_change_password_con_refresh_invalido_no_falla(self, user_con_sucursal):
        """M-BUG-13: si el refresh no se puede blacklistear, el cambio igual procede."""
        client = APIClient()
        client.force_authenticate(user=user_con_sucursal)
        resp = client.post(
            "/api/auth/change-password/",
            {
                "old_password": PASSWORD,
                "new_password": "Nueva.Clave.Segura.99",
                "refresh": "token-invalido",
            },
            format="json",
        )
        assert resp.status_code == 200
        user_con_sucursal.refresh_from_db()
        assert user_con_sucursal.check_password("Nueva.Clave.Segura.99")


# ── dispositivo_accion_view ───────────────────────────────────────────────────


@pytest.fixture
def client_user(user_con_sucursal):
    c = APIClient()
    c.force_authenticate(user=user_con_sucursal)
    return c


class TestDispositivoAccionValidaciones:
    def test_requiere_autenticacion(self):
        resp = APIClient().post(ACCION_URL, {"accion": "x", "id_dispositivo": "y"}, format="json")
        assert resp.status_code == 401

    def test_faltan_parametros_400(self, client_user):
        resp = client_user.post(ACCION_URL, {"accion": "abrir_sesion"}, format="json")
        assert resp.status_code == 400
        assert resp.json()["error"] == "Se requieren accion e id_dispositivo"

    def test_dispositivo_inexistente_404(self, client_user):
        resp = client_user.post(
            ACCION_URL,
            {"accion": "abrir_sesion", "id_dispositivo": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        assert resp.status_code == 404

    def test_dispositivo_de_otro_usuario_404(self, client_user, dispositivo_a, user_b):
        """El dispositivo existe pero pertenece a otro usuario → 404 (authz)."""
        dispositivo_a.creado_por = user_b
        dispositivo_a.save(update_fields=["creado_por"])
        resp = client_user.post(
            ACCION_URL,
            {"accion": "abrir_sesion", "id_dispositivo": str(dispositivo_a.id_dispositivo)},
            format="json",
        )
        assert resp.status_code == 404

    def test_accion_desconocida_400(self, client_user, dispositivo_a):
        resp = client_user.post(
            ACCION_URL,
            {"accion": "volar", "id_dispositivo": str(dispositivo_a.id_dispositivo)},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == 'Acción "volar" no reconocida'


class TestCrearCajaFisica:
    def test_sin_nombre_caja_400(self, client_user, dispositivo_a):
        resp = client_user.post(
            ACCION_URL,
            {"accion": "crear_caja_fisica", "id_dispositivo": str(dispositivo_a.id_dispositivo)},
            format="json",
        )
        assert resp.status_code == 400
        assert "nombre_caja" in resp.json()["error"]

    def test_usuario_sin_permisos_403(self, client_user, dispositivo_a):
        resp = client_user.post(
            ACCION_URL,
            {
                "accion": "crear_caja_fisica",
                "id_dispositivo": str(dispositivo_a.id_dispositivo),
                "nombre_caja": "Caja POS 1",
            },
            format="json",
        )
        assert resp.status_code == 403
        assert CajaFisica.objects.count() == 0

    def test_superusuario_crea_caja_y_abre_sesion_201(
        self, superuser_con_sucursal, dispositivo_a, empresa_a, sucursal_a
    ):
        client = APIClient()
        client.force_authenticate(user=superuser_con_sucursal)
        resp = client.post(
            ACCION_URL,
            {
                "accion": "crear_caja_fisica",
                "id_dispositivo": str(dispositivo_a.id_dispositivo),
                "nombre_caja": "Caja POS 1",
                "tipo_caja": "REGISTRADORA",
            },
            format="json",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        caja = CajaFisica.objects.get(id_caja_fisica=body["caja_fisica"]["id_caja_fisica"])
        assert caja.nombre == "Caja POS 1"
        assert caja.empresa == empresa_a
        assert caja.sucursal == sucursal_a
        assert caja.identificador_dispositivo == FP
        # Asociación usuario-caja predeterminada
        asignacion = CajaFisicaUsuario.objects.get(usuario=superuser_con_sucursal, caja_fisica=caja)
        assert asignacion.es_predeterminada is True
        assert asignacion.puede_abrir_sesion is True
        # El dispositivo queda asociado y la sesión abierta
        dispositivo_a.refresh_from_db()
        assert dispositivo_a.caja_fisica == caja
        sesion = SesionCajaFisica.objects.get(id_sesion=body["sesion"]["id_sesion"])
        assert sesion.estado == "ABIERTA"
        assert sesion.caja_fisica == caja

    def test_error_interno_500_sin_filtrar_detalle(self, superuser_con_sucursal, dispositivo_a):
        client = APIClient()
        client.force_authenticate(user=superuser_con_sucursal)
        with patch(
            "apps.finanzas.models.SesionCajaFisica.abrir_sesion",
            side_effect=RuntimeError("secreto interno"),
        ):
            resp = client.post(
                ACCION_URL,
                {
                    "accion": "crear_caja_fisica",
                    "id_dispositivo": str(dispositivo_a.id_dispositivo),
                    "nombre_caja": "Caja Err",
                },
                format="json",
            )
        assert resp.status_code == 500
        # No se filtra str(e) al cliente (R-CODE-8)
        assert "secreto interno" not in resp.json()["error"]


class TestNoPreguntarCaja:
    def test_marca_flag_y_200(self, client_user, dispositivo_a):
        assert dispositivo_a.preguntar_crear_caja is True
        resp = client_user.post(
            ACCION_URL,
            {"accion": "no_preguntar_caja", "id_dispositivo": str(dispositivo_a.id_dispositivo)},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        dispositivo_a.refresh_from_db()
        assert dispositivo_a.preguntar_crear_caja is False
        assert dispositivo_a.ultima_pregunta_caja is not None


class TestAbrirSesionAccion:
    def test_sin_caja_fisica_400(self, client_user, dispositivo_a):
        resp = client_user.post(
            ACCION_URL,
            {"accion": "abrir_sesion", "id_dispositivo": str(dispositivo_a.id_dispositivo)},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "El dispositivo no tiene caja física asociada"

    def test_con_caja_abre_sesion_200(self, client_user, dispositivo_a, caja_a, user_con_sucursal):
        dispositivo_a.caja_fisica = caja_a
        dispositivo_a.save()
        resp = client_user.post(
            ACCION_URL,
            {"accion": "abrir_sesion", "id_dispositivo": str(dispositivo_a.id_dispositivo)},
            format="json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mensaje"] == "Sesión abierta en Caja Dispositivo"
        sesion = SesionCajaFisica.objects.get(id_sesion=body["sesion"]["id_sesion"])
        assert sesion.usuario == user_con_sucursal
        assert sesion.estado == "ABIERTA"

    def test_error_interno_500(self, client_user, dispositivo_a, caja_a):
        dispositivo_a.caja_fisica = caja_a
        dispositivo_a.save()
        with patch(
            "apps.finanzas.models.SesionCajaFisica.abrir_sesion",
            side_effect=RuntimeError("kaput"),
        ):
            resp = client_user.post(
                ACCION_URL,
                {"accion": "abrir_sesion", "id_dispositivo": str(dispositivo_a.id_dispositivo)},
                format="json",
            )
        assert resp.status_code == 500
        assert "kaput" not in resp.json()["error"]
