"""
Tests M10 — Infraestructura (completando DoD).

Cubre:
  - test_notificacion_solo_visible_para_usuario_propio: aislamiento multi-tenant/usuario
  - test_marcar_notificacion_leida: POST /api/core/notificaciones/{pk}/marcar_leida/
  - test_saas_middleware_bloquea_sin_suscripcion: middleware retorna 402
  - test_saas_middleware_permite_con_suscripcion_activa: middleware permite paso
  - test_saas_middleware_excluye_rutas_admin: rutas excluidas pasan siempre
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from unittest.mock import MagicMock, patch


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def moneda_usd_m10(db):
    from apps.finanzas.models import Moneda
    return Moneda.objects.create(
        nombre="Dólar M10 Test",
        codigo_iso="USD",
        simbolo="$",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def empresa_m10(db, moneda_usd_m10):
    from apps.core.models import Empresa
    return Empresa.objects.create(
        nombre_legal="Empresa M10 Infrastructure C.A.",
        identificador_fiscal="J-66666666-6",
        id_moneda_base=moneda_usd_m10,
    )


@pytest.fixture
def empresa_m10_b(db, moneda_usd_m10):
    from apps.core.models import Empresa
    return Empresa.objects.create(
        nombre_legal="Empresa M10 B C.A.",
        identificador_fiscal="J-77777777-7",
        id_moneda_base=moneda_usd_m10,
    )


@pytest.fixture
def user_m10(db, empresa_m10):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(
        username="user_m10_infra",
        password="testpass123",
        email="user_m10@test.com",
        is_active=True,
    )
    user.empresas.add(empresa_m10)
    return user


@pytest.fixture
def user_m10_b(db, empresa_m10_b):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(
        username="user_m10_infra_b",
        password="testpass123",
        email="user_m10_b@test.com",
        is_active=True,
    )
    user.empresas.add(empresa_m10_b)
    return user


# ── TestNotificacionAislamiento ───────────────────────────────────────────────


@pytest.mark.django_db
class TestNotificacionAislamiento:
    """Verifica que las notificaciones son visibles solo para el usuario/empresa propios."""

    def test_notificacion_solo_visible_para_usuario_propio(
        self, empresa_m10, empresa_m10_b, user_m10, user_m10_b
    ):
        """
        Notificación creada para user_m10/empresa_m10 NO debe aparecer
        en el queryset de user_m10_b/empresa_m10_b.
        """
        from apps.core.models import Notificacion, crear_notificacion
        from apps.core.viewsets import NotificacionViewSet
        from django.test import RequestFactory

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Notificación privada user_m10",
            mensaje="Solo visible para user_m10",
            tipo="INFO",
            usuario=user_m10,
        )

        factory = RequestFactory()
        request_b = factory.get("/api/core/notificaciones/")
        request_b.user = user_m10_b

        viewset = NotificacionViewSet()
        viewset.request = request_b
        viewset.format_kwarg = None

        qs_b = viewset.get_queryset()
        pk_str = str(n.pk)
        ids_en_qs_b = [str(obj.pk) for obj in qs_b]

        assert pk_str not in ids_en_qs_b, (
            "La notificación de user_m10 no debe ser visible para user_m10_b"
        )

    def test_notificacion_visible_para_usuario_correcto(self, empresa_m10, user_m10):
        """
        Notificación creada para user_m10 debe aparecer en su propio queryset.
        """
        from apps.core.models import Notificacion, crear_notificacion
        from apps.core.viewsets import NotificacionViewSet
        from django.test import RequestFactory

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Visible para user_m10",
            mensaje="Mensaje de prueba",
            tipo="ALERTA",
            usuario=user_m10,
        )

        factory = RequestFactory()
        request = factory.get("/api/core/notificaciones/")
        request.user = user_m10

        viewset = NotificacionViewSet()
        viewset.request = request
        viewset.format_kwarg = None

        qs = viewset.get_queryset()
        ids_en_qs = [str(obj.pk) for obj in qs]

        assert str(n.pk) in ids_en_qs, (
            "La notificación de user_m10 debe ser visible en su propio queryset"
        )

    def test_notificacion_broadcast_visible_para_todos_en_empresa(
        self, empresa_m10, user_m10
    ):
        """
        Notificación broadcast (id_usuario=None) debe ser visible para
        todos los usuarios de la empresa.
        """
        from apps.core.models import crear_notificacion
        from apps.core.viewsets import NotificacionViewSet
        from django.test import RequestFactory

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Broadcast empresa M10",
            mensaje="Visible para todos",
            # Sin usuario → broadcast
        )
        assert n.id_usuario is None

        factory = RequestFactory()
        request = factory.get("/api/core/notificaciones/")
        request.user = user_m10

        viewset = NotificacionViewSet()
        viewset.request = request
        viewset.format_kwarg = None

        qs = viewset.get_queryset()
        ids = [str(obj.pk) for obj in qs]
        assert str(n.pk) in ids, "Notificación broadcast debe ser visible para usuarios de la empresa"

    def test_broadcast_no_visible_para_empresa_diferente(
        self, empresa_m10, empresa_m10_b, user_m10_b
    ):
        """
        Notificación broadcast de empresa_m10 NO debe ser visible para user_m10_b
        (que pertenece a empresa_m10_b).
        """
        from apps.core.models import crear_notificacion
        from apps.core.viewsets import NotificacionViewSet
        from django.test import RequestFactory

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Broadcast empresa A",
            mensaje="Solo para empresa A",
        )

        factory = RequestFactory()
        request = factory.get("/api/core/notificaciones/")
        request.user = user_m10_b

        viewset = NotificacionViewSet()
        viewset.request = request
        viewset.format_kwarg = None

        qs = viewset.get_queryset()
        ids = [str(obj.pk) for obj in qs]
        assert str(n.pk) not in ids, (
            "Notificación broadcast de empresa A no debe ser visible para usuario de empresa B"
        )


# ── TestMarcarNotificacionLeida ───────────────────────────────────────────────


@pytest.mark.django_db
class TestMarcarNotificacionLeida:
    """Verifica la acción marcar_leida via API."""

    def test_marcar_notificacion_leida_via_api(self, client, empresa_m10, user_m10):
        """
        POST /api/core/notificaciones/{pk}/marcar_leida/
        debe marcar la notificación como leída y retornar 200.
        """
        from apps.core.models import Notificacion, crear_notificacion

        client.force_login(user_m10)

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Test marcar leída",
            mensaje="Esta notificación debe marcarse como leída",
            tipo="INFO",
            usuario=user_m10,
        )
        assert n.leida is False

        url = f"/api/core/notificaciones/{n.pk}/marcar_leida/"
        response = client.post(url, content_type="application/json")

        assert response.status_code == 200, (
            f"Esperado 200, se obtuvo {response.status_code}: {response.content}"
        )

        n.refresh_from_db()
        assert n.leida is True, "La notificación debe estar marcada como leída"
        assert n.fecha_lectura is not None, "fecha_lectura debe estar establecida"

    def test_notificacion_ya_leida_sigue_funcionando(self, client, empresa_m10, user_m10):
        """
        Marcar como leída una notificación que ya está leída no debe fallar.
        """
        from apps.core.models import Notificacion, crear_notificacion

        client.force_login(user_m10)

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Ya estaba leída",
            mensaje="Esta ya está marcada",
            tipo="INFO",
            usuario=user_m10,
        )
        n.marcar_leida()
        n.refresh_from_db()
        assert n.leida is True

        url = f"/api/core/notificaciones/{n.pk}/marcar_leida/"
        response = client.post(url, content_type="application/json")

        assert response.status_code == 200, (
            f"Marcar leída una ya-leída debe retornar 200, se obtuvo {response.status_code}"
        )

    def test_usuario_no_puede_marcar_notificacion_de_otro_usuario(
        self, client, empresa_m10, user_m10, user_m10_b, empresa_m10_b
    ):
        """
        user_m10_b no debe poder marcar como leída una notificación de user_m10.
        El endpoint debe retornar 404 (objeto no visible en su queryset).
        """
        from apps.core.models import Notificacion, crear_notificacion

        client.force_login(user_m10_b)

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Notificación de user_m10",
            mensaje="No accesible para user_m10_b",
            tipo="INFO",
            usuario=user_m10,
        )

        url = f"/api/core/notificaciones/{n.pk}/marcar_leida/"
        response = client.post(url, content_type="application/json")

        # Debe ser 404 porque el objeto no aparece en el queryset de user_m10_b
        assert response.status_code == 404, (
            f"Usuario de otra empresa/usuario no debe poder acceder a la notificación, "
            f"se obtuvo {response.status_code}"
        )

    def test_modelo_marcar_leida_actualiza_campos(self, empresa_m10, user_m10):
        """
        El método model.marcar_leida() actualiza correctamente leida y fecha_lectura.
        """
        from apps.core.models import crear_notificacion

        n = crear_notificacion(
            empresa=empresa_m10,
            titulo="Test modelo marcar",
            mensaje="Prueba directa del modelo",
            usuario=user_m10,
        )
        assert n.leida is False
        assert n.fecha_lectura is None

        n.marcar_leida()
        n.refresh_from_db()

        assert n.leida is True
        assert n.fecha_lectura is not None

    def test_no_leidas_count_decrece_al_marcar(self, empresa_m10, user_m10):
        """
        El conteo de no_leidas debe decrecer cuando se marca una como leída.
        """
        from apps.core.models import Notificacion, crear_notificacion

        n1 = crear_notificacion(empresa_m10, "No leída 1", "Msg 1", usuario=user_m10)
        n2 = crear_notificacion(empresa_m10, "No leída 2", "Msg 2", usuario=user_m10)

        no_leidas_antes = Notificacion.objects.filter(
            id_empresa=empresa_m10, id_usuario=user_m10, leida=False
        ).count()

        n1.marcar_leida()

        no_leidas_despues = Notificacion.objects.filter(
            id_empresa=empresa_m10, id_usuario=user_m10, leida=False
        ).count()

        assert no_leidas_despues == no_leidas_antes - 1, (
            f"El conteo de no leídas debe decrecer en 1, "
            f"era {no_leidas_antes}, ahora {no_leidas_despues}"
        )


# ── TestSaasMiddleware ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSaasMiddlewareInfrastructure:
    """Verifica el comportamiento del SuscripcionActivaMiddleware."""

    def _make_middleware(self, settings_override=None):
        """Helper: crea el middleware con settings opcionales."""
        from apps.saas.middleware import SuscripcionActivaMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        return SuscripcionActivaMiddleware(get_response), get_response

    def test_middleware_inactivo_permite_todo(self, empresa_m10):
        """Con SAAS_VERIFICAR_SUSCRIPCION=False (default), el middleware no verifica."""
        middleware, get_response = self._make_middleware()

        factory = RequestFactory()
        request = factory.get("/api/ventas/facturas/")
        request.user = MagicMock(is_authenticated=True, id_empresa=empresa_m10)

        response = middleware(request)
        assert response.status_code == 200

    def test_middleware_excluye_rutas_admin(self):
        """Las rutas de admin y auth siempre están excluidas."""
        from apps.saas.middleware import RUTAS_EXCLUIDAS_DEFAULT
        assert "/admin/" in RUTAS_EXCLUIDAS_DEFAULT
        assert "/api/auth/" in RUTAS_EXCLUIDAS_DEFAULT
        assert "/api/saas/" in RUTAS_EXCLUIDAS_DEFAULT

    def test_middleware_activo_bloquea_sin_suscripcion(self, settings, empresa_m10):
        """Con SAAS_VERIFICAR_SUSCRIPCION=True, bloquea empresas sin suscripción con 402."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        from apps.saas.middleware import SuscripcionActivaMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = SuscripcionActivaMiddleware(get_response)

        factory = RequestFactory()
        request = factory.get("/api/ventas/facturas/")
        # El middleware usa user.empresas.first() — mockear correctamente
        request.user = MagicMock(is_authenticated=True, pk="mock-user-pk")
        request.user.empresas.first.return_value = empresa_m10

        response = middleware(request)
        assert response.status_code == 402, (
            f"Sin suscripción activa, el middleware debe retornar 402, "
            f"se obtuvo {response.status_code}"
        )

    def test_middleware_activo_permite_con_suscripcion(self, settings, empresa_m10, moneda_usd_m10):
        """Con SAAS_VERIFICAR_SUSCRIPCION=True y suscripción activa, el middleware permite."""
        from apps.saas.models import Plan, Suscripcion
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        plan = Plan.objects.create(
            nombre="Plan M10 Test",
            nivel="PRO",
            precio_mensual=Decimal("50.00"),
        )
        hoy = date.today()
        Suscripcion.objects.create(
            id_empresa=empresa_m10,
            id_plan=plan,
            estado="ACTIVA",
            fecha_inicio=hoy - timedelta(days=5),
            fecha_fin=hoy + timedelta(days=25),
        )

        from apps.saas.middleware import SuscripcionActivaMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = SuscripcionActivaMiddleware(get_response)

        factory = RequestFactory()
        request = factory.get("/api/ventas/facturas/")
        # El middleware usa user.empresas.first() — mockear correctamente
        request.user = MagicMock(is_authenticated=True, pk="mock-user-pk")
        request.user.empresas.first.return_value = empresa_m10

        response = middleware(request)
        assert response.status_code == 200, (
            f"Con suscripción activa, el middleware debe permitir (200), "
            f"se obtuvo {response.status_code}"
        )

    def test_middleware_permite_rutas_excluidas_sin_suscripcion(
        self, settings, empresa_m10
    ):
        """Rutas excluidas no son verificadas, incluso sin suscripción."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        from apps.saas.middleware import SuscripcionActivaMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = SuscripcionActivaMiddleware(get_response)

        factory = RequestFactory()
        request = factory.get("/api/auth/token/")
        request.user = MagicMock(
            is_authenticated=True,
            id_empresa=empresa_m10,
            pk="mock-user-pk",
        )

        response = middleware(request)
        assert response.status_code == 200, (
            f"Rutas excluidas siempre deben pasar (200), se obtuvo {response.status_code}"
        )

    def test_middleware_permite_usuarios_anonimos(self, settings, empresa_m10):
        """Usuarios anónimos no son verificados."""
        settings.SAAS_VERIFICAR_SUSCRIPCION = True

        from apps.saas.middleware import SuscripcionActivaMiddleware
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        middleware = SuscripcionActivaMiddleware(get_response)

        factory = RequestFactory()
        request = factory.get("/api/ventas/facturas/")
        request.user = MagicMock(is_authenticated=False)

        response = middleware(request)
        assert response.status_code == 200, (
            f"Usuarios anónimos siempre deben pasar (200), se obtuvo {response.status_code}"
        )
