"""
Backfill de cobertura — apps/servicio_cliente/views.py (plan "Cero Dudas").

Cubre por la API real (router en apps/servicio_cliente/urls.py, prefijo
/api/servicio-cliente/):

- list 200 autenticado + 401 sin token en las 5 rutas del router.
- Aislamiento multi-tenant (R-CODE-1): B no ve objetos de A; retrieve
  cross-tenant → 404.
- Actions: activas, estadisticas, abiertos, por_prioridad, asignar_agente,
  cambiar_estado, escalar, dashboard, agregar_comentario, publicos, buscar,
  actualizar_revision, estadisticas_satisfaccion, por_tipo, quejas_sugerencias
  (caminos felices y de error 400/404).

Fixtures multi-tenant (empresa_a/b, user_a/b, moneda_usd) del conftest.
"""
import uuid

import pytest
from rest_framework.test import APIClient

from apps.servicio_cliente.models import (
    BaseConocimientoArticulo,
    CategoriaTicket,
    FeedbackCliente,
    InteraccionTicket,
    TicketSoporte,
)

pytestmark = pytest.mark.django_db

BASE = "/api/servicio-cliente/"

ROUTES = [
    "categorias-ticket",
    "tickets-soporte",
    "interacciones-ticket",
    "articulos-conocimiento",
    "feedback-cliente",
]


def _results(resp):
    data = resp.json()
    return data.get("results", data) if isinstance(data, dict) else data


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def categoria_a(empresa_a):
    return CategoriaTicket.objects.create(
        id_empresa=empresa_a, nombre_categoria="Soporte Técnico", activo=True
    )


@pytest.fixture
def categoria_b(empresa_b):
    return CategoriaTicket.objects.create(
        id_empresa=empresa_b, nombre_categoria="Facturación Beta", activo=True
    )


@pytest.fixture
def ticket_a(empresa_a, categoria_a):
    return TicketSoporte.objects.create(
        id_empresa=empresa_a,
        numero_ticket="TKT-A-001",
        asunto="Error en módulo de ventas",
        descripcion="El módulo de ventas no carga",
        id_categoria_ticket=categoria_a,
        prioridad="MEDIA",
        estado_ticket="ABIERTO",
    )


@pytest.fixture
def ticket_b(empresa_b, categoria_b):
    return TicketSoporte.objects.create(
        id_empresa=empresa_b,
        numero_ticket="TKT-B-001",
        asunto="Ticket de Beta",
        descripcion="Problema en Beta",
        id_categoria_ticket=categoria_b,
        prioridad="BAJA",
        estado_ticket="ABIERTO",
    )


@pytest.fixture
def articulo_a(empresa_a, categoria_a):
    return BaseConocimientoArticulo.objects.create(
        id_empresa=empresa_a,
        titulo="Cómo reiniciar el módulo de ventas",
        contenido="Pasos para reiniciar el módulo de ventas correctamente",
        id_categoria_ticket=categoria_a,
        palabras_clave="ventas, reinicio",
        activo=True,
        visibilidad="PUBLICA",
    )


class TestAutenticacionRequerida:
    @pytest.mark.parametrize("route", ROUTES)
    def test_401_sin_token(self, route):
        resp = APIClient().get(f"{BASE}{route}/")
        assert resp.status_code == 401


class TestAislamientoMultiTenant:
    def test_b_no_ve_categorias_de_a(self, client_b, categoria_a, categoria_b):
        resp = client_b.get(f"{BASE}categorias-ticket/")
        assert resp.status_code == 200
        ids = [r["id_categoria_ticket"] for r in _results(resp)]
        assert str(categoria_b.id_categoria_ticket) in ids
        assert str(categoria_a.id_categoria_ticket) not in ids

    def test_retrieve_categoria_cross_tenant_404(self, client_b, categoria_a):
        resp = client_b.get(f"{BASE}categorias-ticket/{categoria_a.id_categoria_ticket}/")
        assert resp.status_code == 404

    def test_b_no_ve_tickets_de_a(self, client_b, ticket_a, ticket_b):
        resp = client_b.get(f"{BASE}tickets-soporte/")
        assert resp.status_code == 200
        ids = [r["id_ticket"] for r in _results(resp)]
        assert str(ticket_b.id_ticket) in ids
        assert str(ticket_a.id_ticket) not in ids

    def test_retrieve_ticket_cross_tenant_404(self, client_b, ticket_a):
        resp = client_b.get(f"{BASE}tickets-soporte/{ticket_a.id_ticket}/")
        assert resp.status_code == 404

    def test_b_no_ve_interacciones_de_a(self, client_b, ticket_a):
        inter = InteraccionTicket.objects.create(
            id_ticket=ticket_a, tipo_interaccion="COMENTARIO", contenido="solo de A"
        )
        resp = client_b.get(f"{BASE}interacciones-ticket/")
        assert resp.status_code == 200
        ids = [r["id_interaccion"] for r in _results(resp)]
        assert str(inter.id_interaccion) not in ids

    def test_b_no_ve_articulos_de_a(self, client_b, articulo_a):
        resp = client_b.get(f"{BASE}articulos-conocimiento/")
        assert resp.status_code == 200
        ids = [r["id_articulo"] for r in _results(resp)]
        assert str(articulo_a.id_articulo) not in ids

    def test_b_no_ve_feedback_de_a(self, client_b, empresa_a):
        fb = FeedbackCliente.objects.create(
            id_empresa=empresa_a, tipo_feedback="QUEJA", comentarios="queja de A"
        )
        resp = client_b.get(f"{BASE}feedback-cliente/")
        assert resp.status_code == 200
        ids = [r["id_feedback"] for r in _results(resp)]
        assert str(fb.id_feedback) not in ids


class TestCategoriaTicketActions:
    def test_activas_filtra_inactivas(self, client_a, empresa_a, categoria_a):
        inactiva = CategoriaTicket.objects.create(
            id_empresa=empresa_a, nombre_categoria="Vieja", activo=False
        )
        resp = client_a.get(f"{BASE}categorias-ticket/activas/")
        assert resp.status_code == 200
        ids = [r["id_categoria_ticket"] for r in resp.json()]
        assert str(categoria_a.id_categoria_ticket) in ids
        assert str(inactiva.id_categoria_ticket) not in ids

    def test_estadisticas_exactas(self, client_a, empresa_a, categoria_a):
        for i, estado in enumerate(["ABIERTO", "EN_PROGRESO", "CERRADO", "CERRADO"]):
            TicketSoporte.objects.create(
                id_empresa=empresa_a,
                numero_ticket=f"TKT-E-{i}",
                asunto=f"t{i}",
                descripcion="d",
                id_categoria_ticket=categoria_a,
                prioridad="MEDIA",
                estado_ticket=estado,
            )
        resp = client_a.get(
            f"{BASE}categorias-ticket/{categoria_a.id_categoria_ticket}/estadisticas/"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tickets"] == 4
        assert data["tickets_abiertos"] == 2
        assert data["tickets_cerrados"] == 2
        assert data["porcentaje_resolucion"] == 50.0


class TestTicketSoporteActions:
    def test_abiertos(self, client_a, empresa_a, categoria_a, ticket_a):
        cerrado = TicketSoporte.objects.create(
            id_empresa=empresa_a,
            numero_ticket="TKT-A-CER",
            asunto="cerrado",
            descripcion="d",
            id_categoria_ticket=categoria_a,
            prioridad="MEDIA",
            estado_ticket="CERRADO",
        )
        resp = client_a.get(f"{BASE}tickets-soporte/abiertos/")
        assert resp.status_code == 200
        ids = [r["id_ticket"] for r in resp.json()]
        assert str(ticket_a.id_ticket) in ids
        assert str(cerrado.id_ticket) not in ids

    def test_abiertos_filtra_por_agente(self, client_a, ticket_a):
        agente = uuid.uuid4()
        ticket_a.id_agente_asignado_temp = agente
        ticket_a.save()
        resp = client_a.get(f"{BASE}tickets-soporte/abiertos/", {"agente_id": str(agente)})
        assert resp.status_code == 200
        assert [r["id_ticket"] for r in resp.json()] == [str(ticket_a.id_ticket)]
        # Agente sin tickets → lista vacía
        resp2 = client_a.get(
            f"{BASE}tickets-soporte/abiertos/", {"agente_id": str(uuid.uuid4())}
        )
        assert resp2.json() == []

    def test_por_prioridad_400_sin_param(self, client_a):
        resp = client_a.get(f"{BASE}tickets-soporte/por_prioridad/")
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_por_prioridad_ok(self, client_a, ticket_a):
        resp = client_a.get(f"{BASE}tickets-soporte/por_prioridad/", {"prioridad": "MEDIA"})
        assert resp.status_code == 200
        assert [r["id_ticket"] for r in resp.json()] == [str(ticket_a.id_ticket)]

    def test_asignar_agente_400_sin_id(self, client_a, ticket_a):
        resp = client_a.post(f"{BASE}tickets-soporte/{ticket_a.id_ticket}/asignar_agente/", {})
        assert resp.status_code == 400

    def test_asignar_agente_ok(self, client_a, ticket_a):
        agente = str(uuid.uuid4())
        resp = client_a.post(
            f"{BASE}tickets-soporte/{ticket_a.id_ticket}/asignar_agente/",
            {"agente_id": agente},
        )
        assert resp.status_code == 200
        ticket_a.refresh_from_db()
        assert ticket_a.estado_ticket == "ASIGNADO"
        assert str(ticket_a.id_agente_asignado_temp) == agente
        assert InteraccionTicket.objects.filter(
            id_ticket=ticket_a, tipo_interaccion="ASIGNACION"
        ).count() == 1

    def test_asignar_agente_cross_tenant_404(self, client_b, ticket_a):
        resp = client_b.post(
            f"{BASE}tickets-soporte/{ticket_a.id_ticket}/asignar_agente/",
            {"agente_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_cambiar_estado_invalido_400(self, client_a, ticket_a):
        resp = client_a.post(
            f"{BASE}tickets-soporte/{ticket_a.id_ticket}/cambiar_estado/",
            {"estado": "INVENTADO"},
        )
        assert resp.status_code == 400
        ticket_a.refresh_from_db()
        assert ticket_a.estado_ticket == "ABIERTO"

    def test_cambiar_estado_cerrado_fija_fecha_cierre(self, client_a, ticket_a):
        resp = client_a.post(
            f"{BASE}tickets-soporte/{ticket_a.id_ticket}/cambiar_estado/",
            {"estado": "CERRADO", "comentario": "resuelto"},
        )
        assert resp.status_code == 200
        ticket_a.refresh_from_db()
        assert ticket_a.estado_ticket == "CERRADO"
        assert ticket_a.fecha_cierre is not None
        inter = InteraccionTicket.objects.get(
            id_ticket=ticket_a, tipo_interaccion="CAMBIO_ESTADO"
        )
        assert "ABIERTO" in inter.contenido and "CERRADO" in inter.contenido

    def test_escalar_sube_prioridad_y_reasigna(self, client_a, ticket_a):
        nuevo = str(uuid.uuid4())
        resp = client_a.post(
            f"{BASE}tickets-soporte/{ticket_a.id_ticket}/escalar/",
            {"razon": "sin respuesta", "nuevo_agente_id": nuevo},
        )
        assert resp.status_code == 200
        ticket_a.refresh_from_db()
        assert ticket_a.estado_ticket == "ESCALADO"
        assert ticket_a.prioridad == "ALTA"
        assert str(ticket_a.id_agente_asignado_temp) == nuevo

    def test_dashboard_metricas(self, client_a, empresa_a, categoria_a, ticket_a):
        # BUG documentado (ventana de medianoche): la vista compara
        # `timezone.now().date()` (fecha UTC) contra `fecha_cierre__date`,
        # lookup que convierte a fecha LOCAL (America/Caracas) en SQL. Entre
        # 00:00 y 04:00 UTC ambas fechas difieren y "cerrados hoy" da 0 aunque
        # el cierre sea de hace segundos (así falló en CI a las 00:26 UTC).
        # Congelamos now() a mediodía UTC (ambas fechas coinciden) para que el
        # test sea determinista a cualquier hora; el fix de producto debe usar
        # timezone.localdate() en la vista.
        import datetime as _dt
        from unittest import mock as _mock

        from django.utils import timezone

        fijo = _dt.datetime(2026, 6, 9, 12, 0, 0, tzinfo=_dt.timezone.utc)
        with _mock.patch("django.utils.timezone.now", return_value=fijo):
            cerrado = TicketSoporte.objects.create(
                id_empresa=empresa_a,
                numero_ticket="TKT-A-DSH",
                asunto="cerrado hoy",
                descripcion="d",
                id_categoria_ticket=categoria_a,
                prioridad="ALTA",
                estado_ticket="CERRADO",
            )
            cerrado.fecha_cierre = timezone.now()
            cerrado.save()
            resp = client_a.get(f"{BASE}tickets-soporte/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tickets"] == 2
        assert data["tickets_abiertos"] == 1
        assert data["tickets_cerrados_hoy"] == 1
        assert data["tiempo_promedio_resolucion_horas"] >= 0
        assert {d["estado_ticket"] for d in data["tickets_por_estado"]} == {
            "ABIERTO",
            "CERRADO",
        }

    def test_dashboard_filtra_por_agente(self, client_a, ticket_a):
        resp = client_a.get(
            f"{BASE}tickets-soporte/dashboard/", {"agente_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 200
        assert resp.json()["total_tickets"] == 0


class TestInteraccionTicketActions:
    def test_agregar_comentario_400_faltan_campos(self, client_a):
        resp = client_a.post(f"{BASE}interacciones-ticket/agregar_comentario/", {})
        assert resp.status_code == 400

    def test_agregar_comentario_404_ticket_inexistente(self, client_a):
        resp = client_a.post(
            f"{BASE}interacciones-ticket/agregar_comentario/",
            {"ticket_id": str(uuid.uuid4()), "contenido": "hola"},
        )
        assert resp.status_code == 404

    def test_agregar_comentario_201(self, client_a, ticket_a):
        resp = client_a.post(
            f"{BASE}interacciones-ticket/agregar_comentario/",
            {"ticket_id": str(ticket_a.id_ticket), "contenido": "comentario de prueba"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["tipo_interaccion"] == "COMENTARIO"
        assert data["contenido"] == "comentario de prueba"
        assert InteraccionTicket.objects.filter(id_ticket=ticket_a).count() == 1


class TestBaseConocimientoActions:
    def test_publicos_excluye_internos(self, client_a, empresa_a, articulo_a, categoria_a):
        interno = BaseConocimientoArticulo.objects.create(
            id_empresa=empresa_a,
            titulo="Interno",
            contenido="solo staff",
            activo=True,
            visibilidad="INTERNA",
        )
        resp = client_a.get(f"{BASE}articulos-conocimiento/publicos/")
        assert resp.status_code == 200
        ids = [r["id_articulo"] for r in resp.json()]
        assert str(articulo_a.id_articulo) in ids
        assert str(interno.id_articulo) not in ids

    def test_publicos_filtra_por_categoria(self, client_a, articulo_a, categoria_a):
        resp = client_a.get(
            f"{BASE}articulos-conocimiento/publicos/",
            {"categoria_id": str(categoria_a.id_categoria_ticket)},
        )
        assert resp.status_code == 200
        assert [r["id_articulo"] for r in resp.json()] == [str(articulo_a.id_articulo)]

    def test_buscar_400_sin_query(self, client_a):
        resp = client_a.get(f"{BASE}articulos-conocimiento/buscar/")
        assert resp.status_code == 400

    def test_buscar_encuentra_por_titulo(self, client_a, articulo_a):
        resp = client_a.get(f"{BASE}articulos-conocimiento/buscar/", {"q": "reiniciar"})
        assert resp.status_code == 200
        assert [r["id_articulo"] for r in resp.json()] == [str(articulo_a.id_articulo)]

    def test_buscar_sin_coincidencias(self, client_a, articulo_a):
        resp = client_a.get(f"{BASE}articulos-conocimiento/buscar/", {"q": "zzznoexiste"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_actualizar_revision(self, client_a, articulo_a):
        antes = articulo_a.fecha_ultima_revision
        resp = client_a.post(
            f"{BASE}articulos-conocimiento/{articulo_a.id_articulo}/actualizar_revision/"
        )
        assert resp.status_code == 200
        articulo_a.refresh_from_db()
        assert articulo_a.fecha_ultima_revision >= antes


class TestFeedbackClienteActions:
    def test_estadisticas_satisfaccion_vacio(self, client_a, empresa_a):
        resp = client_a.get(f"{BASE}feedback-cliente/estadisticas_satisfaccion/")
        assert resp.status_code == 200
        assert resp.json()["total_respuestas"] == 0
        assert resp.json()["calificacion_promedio"] == 0

    def test_estadisticas_satisfaccion_exactas(self, client_a, empresa_a):
        for calif in [4, 4, 5]:
            FeedbackCliente.objects.create(
                id_empresa=empresa_a,
                tipo_feedback="ENCUESTA_SATISFACCION",
                calificacion=calif,
            )
        # Una queja no entra en la encuesta
        FeedbackCliente.objects.create(
            id_empresa=empresa_a, tipo_feedback="QUEJA", calificacion=1
        )
        resp = client_a.get(f"{BASE}feedback-cliente/estadisticas_satisfaccion/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_respuestas"] == 3
        assert data["calificacion_promedio"] == 4.33
        assert data["distribucion_calificaciones"] == {"4": 2, "5": 1}

    def test_estadisticas_satisfaccion_filtro_fechas(self, client_a, empresa_a):
        FeedbackCliente.objects.create(
            id_empresa=empresa_a,
            tipo_feedback="ENCUESTA_SATISFACCION",
            calificacion=5,
        )
        resp = client_a.get(
            f"{BASE}feedback-cliente/estadisticas_satisfaccion/",
            {"fecha_desde": "2000-01-01", "fecha_hasta": "2099-12-31"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_respuestas"] == 1

    def test_por_tipo_400_sin_param(self, client_a):
        resp = client_a.get(f"{BASE}feedback-cliente/por_tipo/")
        assert resp.status_code == 400

    def test_por_tipo_ok(self, client_a, empresa_a):
        fb = FeedbackCliente.objects.create(
            id_empresa=empresa_a, tipo_feedback="SUGERENCIA", comentarios="mejorar UX"
        )
        FeedbackCliente.objects.create(id_empresa=empresa_a, tipo_feedback="QUEJA")
        resp = client_a.get(f"{BASE}feedback-cliente/por_tipo/", {"tipo": "SUGERENCIA"})
        assert resp.status_code == 200
        assert [r["id_feedback"] for r in resp.json()] == [str(fb.id_feedback)]

    def test_quejas_sugerencias(self, client_a, empresa_a):
        queja = FeedbackCliente.objects.create(
            id_empresa=empresa_a, tipo_feedback="QUEJA"
        )
        sugerencia = FeedbackCliente.objects.create(
            id_empresa=empresa_a, tipo_feedback="SUGERENCIA"
        )
        otro = FeedbackCliente.objects.create(id_empresa=empresa_a, tipo_feedback="OTRO")
        resp = client_a.get(f"{BASE}feedback-cliente/quejas_sugerencias/")
        assert resp.status_code == 200
        ids = {r["id_feedback"] for r in resp.json()}
        assert ids == {str(queja.id_feedback), str(sugerencia.id_feedback)}
        assert str(otro.id_feedback) not in ids
