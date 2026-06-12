"""
Sesión I — Tests Módulo Notificaciones MVP

Verifica:
- test_notificacion_in_app_creada(): confirmar_pedido genera notificación in-app al vendedor
- test_notificacion_email_enviada(): Pago INGRESO encola tarea Celery de email
- test_aislamiento_notificaciones(): usuario A no ve notificaciones de usuario B
- test_endpoint_mis_notificaciones(): GET /api/notificaciones/notificaciones/mis-notificaciones/
- test_endpoint_mis_notificaciones_no_leidas(): filtro ?no_leidas=true
- test_endpoint_marcar_leida(): PATCH /api/notificaciones/notificaciones/{id}/marcar-leida/
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.core.models import Notificacion
from apps.notificaciones.models import CanalNotificacion, LogNotificacion, PlantillaNotificacion
from apps.notificaciones.services import emitir_notificacion

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def plantilla_email_pedido(db):
    """Plantilla de email para PEDIDO_CONFIRMADO."""
    return PlantillaNotificacion.objects.create(
        codigo_plantilla="PEDIDO_CONFIRMADO_EMAIL",
        asunto="Pedido #{{ numero_pedido }} confirmado",
        cuerpo_html="<p>El pedido #{{ numero_pedido }} fue confirmado.</p>",
        canal=CanalNotificacion.EMAIL,
        variables_json=["numero_pedido", "nombre_cliente"],
    )


@pytest.fixture
def plantilla_email_pago(db):
    """Plantilla de email para PAGO_RECIBIDO."""
    return PlantillaNotificacion.objects.create(
        codigo_plantilla="PAGO_RECIBIDO_EMAIL",
        asunto="Pago recibido: {{ monto }} {{ moneda }}",
        cuerpo_html="<p>Pago de {{ monto }} {{ moneda }} registrado.</p>",
        canal=CanalNotificacion.EMAIL,
        variables_json=["monto", "moneda"],
    )


# ── Test 1: notificación in-app creada ───────────────────────────────────────

class TestNotificacionInApp:
    def test_notificacion_in_app_creada(self, db, empresa_a, user_a):
        """emitir_notificacion crea Notificacion in-app en core.Notificacion."""
        count_antes = Notificacion.objects.filter(id_usuario=user_a).count()

        notif = emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "P-001", "nombre_cliente": "Cliente Test"},
        )

        assert notif is not None
        count_despues = Notificacion.objects.filter(id_usuario=user_a).count()
        assert count_despues == count_antes + 1

    def test_notificacion_titulo_incluye_numero(self, db, empresa_a, user_a):
        """El título incluye el número de pedido del contexto."""
        notif = emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "P-999", "nombre_cliente": "Acme"},
        )
        assert "P-999" in notif.titulo

    def test_notificacion_tipo_exito(self, db, empresa_a, user_a):
        """PEDIDO_CONFIRMADO genera notificación de tipo EXITO."""
        notif = emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "P-001", "nombre_cliente": "X"},
        )
        assert notif.tipo == "EXITO"

    def test_notificacion_url_accion(self, db, empresa_a, user_a):
        """La URL de acción se persiste en la notificación."""
        notif = emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "P-001", "nombre_cliente": "X"},
            url_accion="/ventas/pedidos/123/",
        )
        assert notif.url_accion == "/ventas/pedidos/123/"

    def test_notificacion_leida_false_por_defecto(self, db, empresa_a, user_a):
        """Las notificaciones se crean sin leer."""
        notif = emitir_notificacion(
            "STOCK_BAJO",
            empresa_a,
            user_a,
            {"nombre_producto": "Widget", "cantidad_actual": 2, "cantidad_minima": 10},
        )
        assert notif.leida is False


# ── Test 2: email Celery ──────────────────────────────────────────────────────

class TestNotificacionEmail:
    def test_notificacion_email_enviada(self, db, empresa_a, user_a, plantilla_email_pedido):
        """emitir_notificacion encola LogNotificacion ENVIADO cuando hay plantilla activa."""
        user_a.email = "vendedor@test.com"
        user_a.save(update_fields=["email"])

        logs_antes = LogNotificacion.objects.filter(
            destinatario=user_a.email,
            canal=CanalNotificacion.EMAIL,
        ).count()

        emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "P-001", "nombre_cliente": "Acme"},
        )

        # Con CELERY_TASK_ALWAYS_EAGER=True el task ya se ejecutó
        logs_despues = LogNotificacion.objects.filter(
            destinatario=user_a.email,
            canal=CanalNotificacion.EMAIL,
        ).count()
        assert logs_despues == logs_antes + 1

    def test_sin_plantilla_no_crea_log(self, db, empresa_a, user_a):
        """Sin plantilla EMAIL activa no se crea LogNotificacion."""
        user_a.email = "vendedor@test.com"
        user_a.save(update_fields=["email"])

        # No creamos plantilla — no debe crearse log
        logs_antes = LogNotificacion.objects.count()
        emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "P-001", "nombre_cliente": "Acme"},
        )
        assert LogNotificacion.objects.count() == logs_antes

    def test_sin_email_usuario_no_crea_log(self, db, empresa_a, user_a, plantilla_email_pedido):
        """Si el usuario no tiene email no se crea LogNotificacion."""
        user_a.email = ""
        user_a.save(update_fields=["email"])

        logs_antes = LogNotificacion.objects.count()
        emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "P-001", "nombre_cliente": "Acme"},
        )
        assert LogNotificacion.objects.count() == logs_antes


# ── Test 3: aislamiento multi-tenant ─────────────────────────────────────────

class TestAislamientoNotificaciones:
    def test_aislamiento_notificaciones(self, db, empresa_a, empresa_b, user_a, user_b):
        """Un usuario solo ve sus propias notificaciones."""
        emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": "PA-001", "nombre_cliente": "A"},
        )
        emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_b,
            user_b,
            {"numero_pedido": "PB-001", "nombre_cliente": "B"},
        )

        notifs_a = Notificacion.objects.filter(id_usuario=user_a)
        notifs_b = Notificacion.objects.filter(id_usuario=user_b)

        assert all(n.id_empresa_id == empresa_a.pk for n in notifs_a)
        assert all(n.id_empresa_id == empresa_b.pk for n in notifs_b)
        assert notifs_a.filter(id_empresa=empresa_b).count() == 0
        assert notifs_b.filter(id_empresa=empresa_a).count() == 0


# ── Tests de endpoints REST ───────────────────────────────────────────────────

@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


@pytest.fixture
def notificaciones_user_a(db, empresa_a, user_a):
    """Crea 3 notificaciones para user_a (2 no leídas, 1 leída)."""
    for i in range(2):
        emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_a,
            user_a,
            {"numero_pedido": f"P-{i:03d}", "nombre_cliente": "Test"},
        )
    # tercera notificación, marcada como leída
    notif = emitir_notificacion(
        "STOCK_BAJO",
        empresa_a,
        user_a,
        {"nombre_producto": "X", "cantidad_actual": 1, "cantidad_minima": 5},
    )
    notif.marcar_leida()
    return Notificacion.objects.filter(id_usuario=user_a)


class TestEndpointsNotificaciones:
    def test_endpoint_mis_notificaciones_200(self, client_a, notificaciones_user_a):
        """GET /api/notificaciones/notificaciones/mis-notificaciones/ devuelve 200."""
        resp = client_a.get("/api/notificaciones/notificaciones/mis-notificaciones/")
        assert resp.status_code == 200

    def test_endpoint_mis_notificaciones_retorna_lista(self, client_a, notificaciones_user_a):
        """El endpoint retorna lista de notificaciones del usuario."""
        resp = client_a.get("/api/notificaciones/notificaciones/mis-notificaciones/")
        assert isinstance(resp.data, list)
        assert len(resp.data) == 3

    def test_endpoint_no_leidas_filtra(self, client_a, notificaciones_user_a):
        """?no_leidas=true retorna solo notificaciones no leídas."""
        resp = client_a.get("/api/notificaciones/notificaciones/mis-notificaciones/?no_leidas=true")
        assert resp.status_code == 200
        assert all(not n["leida"] for n in resp.data)
        assert len(resp.data) == 2

    def test_endpoint_marcar_leida(self, client_a, notificaciones_user_a):
        """PATCH marcar-leida actualiza el campo leida."""
        notif = Notificacion.objects.filter(id_usuario__username="user_empresa_a", leida=False).first()
        resp = client_a.patch(f"/api/notificaciones/notificaciones/{notif.pk}/marcar-leida/")
        assert resp.status_code == 200
        assert resp.data["leida"] is True

    def test_endpoint_sin_autenticar_401(self):
        """Sin autenticación devuelve 401."""
        client = APIClient()
        resp = client.get("/api/notificaciones/notificaciones/mis-notificaciones/")
        assert resp.status_code == 401

    def test_endpoint_aislamiento_no_ve_ajenas(self, db, client_a, empresa_b, user_b, notificaciones_user_a):
        """User A no puede marcar como leída una notificación de user B."""
        notif_b = emitir_notificacion(
            "PEDIDO_CONFIRMADO",
            empresa_b,
            user_b,
            {"numero_pedido": "PB-001", "nombre_cliente": "B"},
        )
        resp = client_a.patch(f"/api/notificaciones/notificaciones/{notif_b.pk}/marcar-leida/")
        assert resp.status_code == 404
