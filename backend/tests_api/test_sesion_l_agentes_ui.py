"""
Sesión L — Tests UI de Agentes/Sugerencias

Verifica:
- test_sugerencias_activas_200(): GET /api/agentes/predicciones/sugerencias-activas/ devuelve 200
- test_sugerencias_activas_estructura(): La respuesta tiene claves 'sugerencias' y 'total'
- test_sugerencias_activas_solo_pendientes(): Solo aparecen predicciones con resultado_humano=pendiente
- test_sugerencias_activas_limite(): ?limite=2 retorna máximo 2 sugerencias
- test_sugerencias_activas_filtro_agente(): ?agente= filtra correctamente
- test_sugerencias_activas_aislamiento(): Usuario B no ve sugerencias de empresa A
- test_sugerencias_sin_auth_401(): Sin autenticación retorna 401
- test_responder_aceptar(): POST /responder/ con accion=aceptar cambia resultado_humano=aceptada
- test_responder_rechazar(): POST /responder/ con accion=rechazar cambia resultado_humano=rechazada
- test_responder_accion_invalida_400(): accion=ignorar retorna 400
- test_responder_ya_procesada_409(): Responder dos veces retorna 409
- test_responder_ajena_404(): Usuario B no puede responder predicción de empresa A
- test_generar_sugerencias_tarea_celery(): La tarea Celery corre sin excepciones (eager mode)
"""
import datetime

import pytest
from rest_framework.test import APIClient

from apps.agentes.models import PrediccionAgente


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
def prediccion_pendiente(db, empresa_a):
    return PrediccionAgente.objects.create(
        id_empresa=empresa_a,
        agente="cobranza_estratega",
        input_texto="Cliente X debe $5000",
        input_monto="5000.00",
        input_metadata={"cliente_nombre": "Cliente X", "cxc_id": "abc-123"},
        categoria_predicha="contactar_cliente",
        confianza=0.92,
        razonamiento="Factura vencida hace 30 días con monto significativo.",
        resultado_humano="pendiente",
    )


@pytest.fixture
def prediccion_aceptada(db, empresa_a):
    return PrediccionAgente.objects.create(
        id_empresa=empresa_a,
        agente="reorden_sugeridor",
        input_texto="Producto Y bajo stock",
        input_monto=None,
        input_metadata={"nombre_producto": "Producto Y"},
        categoria_predicha="reponer_stock",
        confianza=0.85,
        razonamiento="Stock por debajo del mínimo configurado.",
        resultado_humano="aceptada",
    )


@pytest.fixture
def prediccion_reorden(db, empresa_a):
    return PrediccionAgente.objects.create(
        id_empresa=empresa_a,
        agente="reorden_sugeridor",
        input_texto="Producto Z stock bajo",
        input_metadata={"nombre_producto": "Producto Z", "producto_id": "prod-z-id"},
        categoria_predicha="reponer_stock",
        confianza=0.78,
        razonamiento="Stock crítico.",
        resultado_humano="pendiente",
    )


URL_SUGERENCIAS = "/api/agentes/predicciones/sugerencias-activas/"


def _url_responder(pk):
    return f"/api/agentes/predicciones/{pk}/responder/"


# ── Sugerencias Activas ───────────────────────────────────────────────────────

class TestSugerenciasActivas:
    def test_sugerencias_activas_200(self, client_a, prediccion_pendiente):
        resp = client_a.get(URL_SUGERENCIAS)
        assert resp.status_code == 200

    def test_sugerencias_activas_estructura(self, client_a, prediccion_pendiente):
        resp = client_a.get(URL_SUGERENCIAS)
        assert "sugerencias" in resp.data
        assert "total" in resp.data

    def test_sugerencias_activas_contiene_prediccion(self, client_a, prediccion_pendiente):
        resp = client_a.get(URL_SUGERENCIAS)
        ids = [s["id"] for s in resp.data["sugerencias"]]
        assert str(prediccion_pendiente.id_prediccion) in ids

    def test_sugerencias_activas_solo_pendientes(self, client_a, prediccion_pendiente, prediccion_aceptada):
        """Las predicciones ya aceptadas/rechazadas NO deben aparecer."""
        resp = client_a.get(URL_SUGERENCIAS)
        ids = [s["id"] for s in resp.data["sugerencias"]]
        assert str(prediccion_pendiente.id_prediccion) in ids
        assert str(prediccion_aceptada.id_prediccion) not in ids

    def test_sugerencias_activas_limite(self, client_a, prediccion_pendiente, prediccion_reorden):
        resp = client_a.get(URL_SUGERENCIAS, {"limite": 1})
        assert len(resp.data["sugerencias"]) <= 1

    def test_sugerencias_activas_filtro_agente(self, client_a, prediccion_pendiente, prediccion_reorden):
        resp = client_a.get(URL_SUGERENCIAS, {"agente": "reorden_sugeridor"})
        agentes = [s["agente"] for s in resp.data["sugerencias"]]
        assert all(a == "reorden_sugeridor" for a in agentes)

    def test_sugerencias_campos_presentes(self, client_a, prediccion_pendiente):
        resp = client_a.get(URL_SUGERENCIAS)
        sugerencia = next(s for s in resp.data["sugerencias"] if s["id"] == str(prediccion_pendiente.id_prediccion))
        for campo in ["id", "agente", "titulo", "descripcion", "confianza", "fecha"]:
            assert campo in sugerencia, f"Falta campo: {campo}"

    def test_sugerencias_activas_aislamiento(self, client_b, prediccion_pendiente):
        """Usuario B no debe ver predicciones de empresa A."""
        resp = client_b.get(URL_SUGERENCIAS)
        assert resp.status_code in (200, 403)
        if resp.status_code == 200:
            ids = [s["id"] for s in resp.data.get("sugerencias", [])]
            assert str(prediccion_pendiente.id_prediccion) not in ids

    def test_sugerencias_sin_auth_401(self):
        resp = APIClient().get(URL_SUGERENCIAS)
        assert resp.status_code == 401


# ── Responder ─────────────────────────────────────────────────────────────────

class TestResponder:
    def test_responder_aceptar(self, client_a, prediccion_pendiente):
        resp = client_a.post(
            _url_responder(prediccion_pendiente.id_prediccion),
            {"accion": "aceptar"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["resultado_humano"] == "aceptada"
        prediccion_pendiente.refresh_from_db()
        assert prediccion_pendiente.resultado_humano == "aceptada"

    def test_responder_rechazar(self, client_a, prediccion_reorden):
        resp = client_a.post(
            _url_responder(prediccion_reorden.id_prediccion),
            {"accion": "rechazar", "comentario": "No es necesario reordenar ahora"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["resultado_humano"] == "rechazada"
        prediccion_reorden.refresh_from_db()
        assert prediccion_reorden.resultado_humano == "rechazada"

    def test_responder_accion_invalida_400(self, client_a, prediccion_pendiente):
        resp = client_a.post(
            _url_responder(prediccion_pendiente.id_prediccion),
            {"accion": "ignorar"},
            format="json",
        )
        assert resp.status_code == 400

    def test_responder_ya_procesada_409(self, client_a, prediccion_pendiente):
        """Responder una sugerencia ya procesada retorna 409."""
        client_a.post(
            _url_responder(prediccion_pendiente.id_prediccion),
            {"accion": "aceptar"},
            format="json",
        )
        # Segunda vez
        resp = client_a.post(
            _url_responder(prediccion_pendiente.id_prediccion),
            {"accion": "rechazar"},
            format="json",
        )
        assert resp.status_code == 409

    def test_responder_no_afecta_otras_predicciones(self, client_a, prediccion_pendiente, prediccion_reorden):
        """Responder una predicción no cambia las otras."""
        client_a.post(
            _url_responder(prediccion_pendiente.id_prediccion),
            {"accion": "aceptar"},
            format="json",
        )
        prediccion_reorden.refresh_from_db()
        assert prediccion_reorden.resultado_humano == "pendiente"

    def test_responder_ajena_404(self, client_b, prediccion_pendiente):
        """Usuario B no puede responder predicción de empresa A."""
        resp = client_b.post(
            _url_responder(prediccion_pendiente.id_prediccion),
            {"accion": "aceptar"},
            format="json",
        )
        assert resp.status_code == 404

    def test_responder_sin_auth_401(self, prediccion_pendiente):
        resp = APIClient().post(
            _url_responder(prediccion_pendiente.id_prediccion),
            {"accion": "aceptar"},
            format="json",
        )
        assert resp.status_code == 401


# ── Tarea Celery ──────────────────────────────────────────────────────────────

class TestGenerarSugerenciasDiarias:
    def test_tarea_celery_ejecuta_sin_excepcion(self, db, empresa_a):
        """La tarea generar_sugerencias_diarias corre en modo eager sin lanzar excepción."""
        from apps.agentes.tasks import generar_sugerencias_diarias
        # En modo CELERY_TASK_ALWAYS_EAGER (configurado en conftest), se ejecuta sync
        result = generar_sugerencias_diarias.delay()
        assert result is not None
        # La tarea retorna un dict con total_sugerencias (puede ser 0 si no hay CxC/stock)
        retval = result.get()
        assert "total_sugerencias" in retval
        assert "empresas" in retval

    def test_tarea_celery_idempotente(self, db, empresa_a):
        """Ejecutar dos veces no lanza excepciones."""
        from apps.agentes.tasks import generar_sugerencias_diarias
        r1 = generar_sugerencias_diarias.delay().get()
        r2 = generar_sugerencias_diarias.delay().get()
        assert r1["empresas"] == r2["empresas"]
