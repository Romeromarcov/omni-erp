"""
Tests de cobertura de las views del Integration Hub (apps/integration_hub/views.py).

Rutas bajo /api/integration-hub/ (ver config/urls.py).
Todo acceso al sistema externo se mockea vía registry.get_connector — CERO red real.
"""
import pytest
from unittest.mock import MagicMock, patch

from django.utils import timezone
from rest_framework.test import APIClient

from apps.integration_hub.connectors.base import TestConnectionResult
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)

pytestmark = pytest.mark.django_db

BASE = "/api/integration-hub"


@pytest.fixture
def proveedor(db):
    return ConectorProveedor.objects.create(
        codigo="fake_views",
        nombre="Fake Views",
        capacidades=["contactos", "productos"],
    )


@pytest.fixture
def instancia(db, empresa_a, proveedor):
    return ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor,
        nombre="Conector Views",
        configuracion={"host": "fake.local", "user": "u", "api_key": "k"},
        estado="activo",
        entidades_activas=["contactos"],
    )


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


@pytest.fixture
def client_b(user_b):
    client = APIClient()
    client.force_authenticate(user=user_b)
    return client


def _mock_conector(registros=None):
    """Conector mockeado que soporta contactos y devuelve registros fijos.

    Nota: el default devuelve UN registro (no lista vacía) porque el SyncEngine
    actual crashea con pull vacío (bug 'procesados' — ver test_hub_sync_engine).
    """
    if registros is None:
        registros = [{"id_externo": "1", "nombre": "Uno", "_checksum": "c1"}]
    conector = MagicMock()
    conector.PROVIDER_NAME = "MockProv"
    conector.supports.return_value = True
    conector.pull_contactos.return_value = registros
    conector.pull_productos.return_value = registros
    return conector


class TestProveedoresEndpoint:
    def test_lista_proveedores_activos(self, client_a, proveedor):
        resp = client_a.get(f"{BASE}/proveedores/")
        assert resp.status_code == 200
        codigos = [p["codigo"] for p in resp.data]
        assert "fake_views" in codigos

    def test_proveedor_inactivo_no_aparece(self, client_a, proveedor):
        ConectorProveedor.objects.create(
            codigo="apagado", nombre="Apagado", activo=False
        )
        resp = client_a.get(f"{BASE}/proveedores/")
        assert "apagado" not in [p["codigo"] for p in resp.data]

    def test_requiere_autenticacion(self, proveedor):
        resp = APIClient().get(f"{BASE}/proveedores/")
        assert resp.status_code in (401, 403)


class TestInstanciasCRUD:
    def test_crear_instancia_asigna_empresa_y_estado(self, client_a, empresa_a, proveedor):
        payload = {
            "id_proveedor": str(proveedor.id_proveedor),
            "nombre": "Mi Conector Nuevo",
            "configuracion": {"host": "h.local", "user": "u@x.com", "api_key": "secreta"},
            "entidades_activas": ["contactos"],
        }
        resp = client_a.post(f"{BASE}/instancias/", payload, format="json")
        assert resp.status_code == 201

        creada = ConectorInstancia.objects.get(nombre="Mi Conector Nuevo")
        assert creada.id_empresa_id == empresa_a.pk
        assert creada.estado == "configurando"
        assert creada.get_config()["api_key"] == "secreta"

    def test_crear_sin_host_falla(self, client_a, proveedor):
        payload = {
            "id_proveedor": str(proveedor.id_proveedor),
            "nombre": "Sin Host",
            "configuracion": {"user": "u", "api_key": "k"},
        }
        resp = client_a.post(f"{BASE}/instancias/", payload, format="json")
        assert resp.status_code == 400
        assert "host" in str(resp.data["configuracion"])

    def test_crear_sin_api_key_falla(self, client_a, proveedor):
        payload = {
            "id_proveedor": str(proveedor.id_proveedor),
            "nombre": "Sin Key",
            "configuracion": {"host": "h", "user": "u"},
        }
        resp = client_a.post(f"{BASE}/instancias/", payload, format="json")
        assert resp.status_code == 400
        assert "api_key" in str(resp.data["configuracion"])

    def test_crear_nombre_duplicado_falla(self, client_a, instancia, proveedor):
        payload = {
            "id_proveedor": str(proveedor.id_proveedor),
            "nombre": instancia.nombre,
            "configuracion": {"host": "h", "user": "u", "api_key": "k"},
        }
        resp = client_a.post(f"{BASE}/instancias/", payload, format="json")
        assert resp.status_code == 400
        assert "Ya existe un conector" in str(resp.data["nombre"])

    def test_detalle_no_expone_api_key(self, client_a, instancia):
        resp = client_a.get(f"{BASE}/instancias/{instancia.id_conector}/")
        assert resp.status_code == 200
        assert resp.data["configuracion_publica"] == {
            "host": "fake.local",
            "db": "",
            "user": "u",
            "timeout": 30,
        }
        assert "api_key" not in str(resp.data)

    def test_aislamiento_empresa_b_no_ve_instancia_de_a(self, client_b, instancia):
        resp = client_b.get(f"{BASE}/instancias/")
        assert resp.status_code == 200
        resultados = resp.data.get("results", resp.data)
        assert resultados == [] or len(resultados) == 0

        detalle = client_b.get(f"{BASE}/instancias/{instancia.id_conector}/")
        assert detalle.status_code == 404


class TestTestConnectionAction:
    def test_conexion_exitosa_activa_instancia(self, client_a, instancia):
        conector = _mock_conector()
        conector.test_connection.return_value = TestConnectionResult(
            success=True, message="Conexión exitosa con Odoo 17.0",
            version="17.0", details={"uid": 2},
        )
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.post(f"{BASE}/instancias/{instancia.id_conector}/test/")

        assert resp.status_code == 200
        assert resp.data == {
            "success": True,
            "message": "Conexión exitosa con Odoo 17.0",
            "version": "17.0",
            "details": {"uid": 2},
        }
        instancia.refresh_from_db()
        assert instancia.estado == "activo"
        assert instancia.version_detectada == "17.0"
        assert instancia.ultimo_test_conexion is not None

    def test_conexion_fallida_marca_error(self, client_a, instancia):
        conector = _mock_conector()
        conector.test_connection.return_value = TestConnectionResult(
            success=False, message="Credenciales inválidas"
        )
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.post(f"{BASE}/instancias/{instancia.id_conector}/test/")

        assert resp.status_code == 200
        assert resp.data["success"] is False
        instancia.refresh_from_db()
        assert instancia.estado == "error"
        assert instancia.mensaje_estado == "Credenciales inválidas"

    def test_excepcion_retorna_502(self, client_a, instancia):
        with patch.object(
            registry, "get_connector", side_effect=RuntimeError("sin conector")
        ):
            resp = client_a.post(f"{BASE}/instancias/{instancia.id_conector}/test/")

        assert resp.status_code == 502
        assert resp.data["success"] is False
        # SEC-M4 (R-CODE-8): el detalle interno NO se filtra al cliente.
        assert "sin conector" not in resp.data["message"]
        instancia.refresh_from_db()
        assert instancia.estado == "error"
        assert "sin conector" not in instancia.mensaje_estado


class TestTriggerSyncAction:
    def test_instancia_en_error_rechaza_sync(self, client_a, instancia):
        instancia.estado = "error"
        instancia.save(update_fields=["estado"])
        resp = client_a.post(
            f"{BASE}/instancias/{instancia.id_conector}/sync/",
            {"tipo_entidad": "contactos"},
            format="json",
        )
        assert resp.status_code == 400
        assert "estado de error" in resp.data["error"]

    def test_tipo_entidad_invalido_400(self, client_a, instancia):
        resp = client_a.post(
            f"{BASE}/instancias/{instancia.id_conector}/sync/",
            {"tipo_entidad": "criptomonedas"},
            format="json",
        )
        assert resp.status_code == 400

    def test_entidad_no_habilitada_400(self, client_a, instancia):
        # entidades_activas = ["contactos"] → productos no habilitado
        resp = client_a.post(
            f"{BASE}/instancias/{instancia.id_conector}/sync/",
            {"tipo_entidad": "productos"},
            format="json",
        )
        assert resp.status_code == 400
        assert "no está habilitada" in resp.data["error"]

    def test_sync_exitoso_crea_job_y_lo_ejecuta_eager(self, client_a, instancia, user_a):
        conector = _mock_conector()
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.post(
                f"{BASE}/instancias/{instancia.id_conector}/sync/",
                {"tipo_entidad": "contactos", "sync_completo": True, "desde": "2024-01-15"},
                format="json",
            )

        assert resp.status_code == 202
        job = JobSincronizacion.objects.get(id_instancia=instancia)
        assert job.tipo_entidad == "contactos"
        assert job.direccion == "inbound"
        assert job.iniciado_por_id == user_a.pk
        assert job.parametros == {"sync_completo": True, "desde": "2024-01-15"}
        # Con CELERY_TASK_ALWAYS_EAGER el job se ejecutó sincrónicamente
        assert job.estado == "completado"
        assert job.celery_task_id != ""

    def test_sync_fallback_sincronico_si_celery_falla(self, client_a, instancia):
        conector = _mock_conector()
        with patch.object(registry, "get_connector", return_value=conector), patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay",
            side_effect=RuntimeError("broker caído"),
        ):
            resp = client_a.post(
                f"{BASE}/instancias/{instancia.id_conector}/sync/",
                {"tipo_entidad": "contactos"},
                format="json",
            )

        assert resp.status_code == 202
        assert resp.data["estado"] == "completado"
        job = JobSincronizacion.objects.get(id_instancia=instancia)
        assert job.estado == "completado"
        assert job.celery_task_id == ""

    def test_entidades_activas_vacias_permite_cualquier_entidad(self, client_a, instancia):
        instancia.entidades_activas = []
        instancia.save(update_fields=["entidades_activas"])
        conector = _mock_conector()
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.post(
                f"{BASE}/instancias/{instancia.id_conector}/sync/",
                {"tipo_entidad": "productos"},
                format="json",
            )
        assert resp.status_code == 202


class TestJobsYEntidadesActions:
    def test_list_jobs_de_instancia(self, client_a, instancia):
        JobSincronizacion.objects.create(
            id_instancia=instancia,
            tipo_entidad="contactos",
            estado="completado",
            iniciado_en=timezone.now(),
        )
        resp = client_a.get(f"{BASE}/instancias/{instancia.id_conector}/jobs/")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["tipo_entidad"] == "contactos"
        assert resp.data[0]["instancia_nombre"] == "Conector Views"

    def test_list_entidades_por_tipo(self, client_a, instancia):
        EntidadSincronizada.objects.create(
            id_instancia=instancia,
            tipo_entidad="contactos",
            id_externo="55",
            id_omni="uuid-omni-55",
        )
        EntidadSincronizada.objects.create(
            id_instancia=instancia,
            tipo_entidad="productos",
            id_externo="99",
        )
        resp = client_a.get(
            f"{BASE}/instancias/{instancia.id_conector}/entidades/contactos/"
        )
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["id_externo"] == "55"
        assert resp.data[0]["id_omni"] == "uuid-omni-55"


class TestPreviewAction:
    def test_preview_retorna_muestra(self, client_a, instancia):
        registros = [{"id_externo": str(i), "nombre": f"C{i}"} for i in range(15)]
        conector = _mock_conector(registros=registros)
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.get(
                f"{BASE}/instancias/{instancia.id_conector}/preview/contactos/"
            )
        assert resp.status_code == 200
        assert resp.data["tipo_entidad"] == "contactos"
        assert len(resp.data["muestra"]) == 10  # máximo 10 en preview
        conector.pull_contactos.assert_called_once_with(desde=None)

    def test_preview_entidad_no_soportada_400(self, client_a, instancia):
        conector = _mock_conector()
        conector.supports.return_value = False
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.get(
                f"{BASE}/instancias/{instancia.id_conector}/preview/contactos/"
            )
        assert resp.status_code == 400
        assert "no soportado" in resp.data["error"]

    def test_preview_sin_metodo_pull_400(self, client_a, instancia):
        conector = _mock_conector()
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.get(
                f"{BASE}/instancias/{instancia.id_conector}/preview/empleados/"
            )
        assert resp.status_code == 400
        assert "Sin método pull" in resp.data["error"]

    def test_preview_error_de_registry_502(self, client_a, instancia):
        with patch.object(
            registry, "get_connector", side_effect=RuntimeError("config rota")
        ):
            resp = client_a.get(
                f"{BASE}/instancias/{instancia.id_conector}/preview/contactos/"
            )
        assert resp.status_code == 502
        # SEC-M4 (R-CODE-8): el detalle interno NO se filtra al cliente.
        assert "config rota" not in resp.data["error"]

    def test_preview_error_del_conector_502(self, client_a, instancia):
        conector = _mock_conector()
        conector.pull_contactos.side_effect = RuntimeError("timeout externo")
        with patch.object(registry, "get_connector", return_value=conector):
            resp = client_a.get(
                f"{BASE}/instancias/{instancia.id_conector}/preview/contactos/"
            )
        assert resp.status_code == 502
        # SEC-M4 (R-CODE-8): el detalle interno NO se filtra al cliente.
        assert "timeout externo" not in resp.data["error"]


class TestJobViewSet:
    def test_lista_jobs_solo_de_mi_empresa(self, client_a, client_b, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="completado"
        )
        resp_a = client_a.get(f"{BASE}/jobs/")
        assert resp_a.status_code == 200
        ids_a = [j["id_job"] for j in resp_a.data.get("results", resp_a.data)]
        assert str(job.id_job) in [str(i) for i in ids_a]

        resp_b = client_b.get(f"{BASE}/jobs/")
        ids_b = [j["id_job"] for j in resp_b.data.get("results", resp_b.data)]
        assert str(job.id_job) not in [str(i) for i in ids_b]

    def test_logs_de_un_job(self, client_a, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="completado"
        )
        LogDetalleSincronizacion.objects.create(
            id_job=job, id_externo="3", id_omni="o-3", operacion="crear"
        )
        resp = client_a.get(f"{BASE}/jobs/{job.id_job}/logs/")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["id_externo"] == "3"
        assert resp.data[0]["operacion"] == "crear"

    def test_cancelar_job_pendiente(self, client_a, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="pendiente"
        )
        resp = client_a.post(f"{BASE}/jobs/{job.id_job}/cancelar/")
        assert resp.status_code == 200
        job.refresh_from_db()
        assert job.estado == "cancelado"
        assert job.completado_en is not None

    def test_cancelar_job_con_task_id_revoca_celery(self, client_a, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia,
            tipo_entidad="contactos",
            estado="en_progreso",
            celery_task_id="task-abc-123",
        )
        with patch("config.celery.app.control.revoke") as mock_revoke:
            resp = client_a.post(f"{BASE}/jobs/{job.id_job}/cancelar/")
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with("task-abc-123", terminate=True)
        job.refresh_from_db()
        assert job.estado == "cancelado"

    def test_cancelar_job_si_revoke_falla_igual_cancela(self, client_a, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia,
            tipo_entidad="contactos",
            estado="en_progreso",
            celery_task_id="task-xyz",
        )
        with patch(
            "config.celery.app.control.revoke", side_effect=RuntimeError("broker caído")
        ):
            resp = client_a.post(f"{BASE}/jobs/{job.id_job}/cancelar/")
        # El error de revoke se traga (except pass) y el job se cancela igual
        assert resp.status_code == 200
        job.refresh_from_db()
        assert job.estado == "cancelado"

    def test_cancelar_job_completado_400(self, client_a, instancia):
        job = JobSincronizacion.objects.create(
            id_instancia=instancia, tipo_entidad="contactos", estado="completado"
        )
        resp = client_a.post(f"{BASE}/jobs/{job.id_job}/cancelar/")
        assert resp.status_code == 400
        assert "completado" in resp.data["error"]


class TestStatusEndpoint:
    def test_status_cuenta_conectores_y_jobs(self, client_a, empresa_a, proveedor, instancia):
        ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            nombre="Con Error",
            configuracion={"host": "x", "user": "u", "api_key": "k"},
            estado="error",
        )
        JobSincronizacion.objects.create(
            id_instancia=instancia,
            tipo_entidad="contactos",
            estado="completado",
            iniciado_en=timezone.now(),
        )
        JobSincronizacion.objects.create(
            id_instancia=instancia,
            tipo_entidad="productos",
            estado="fallido",
            iniciado_en=timezone.now(),
        )

        resp = client_a.get(f"{BASE}/status/")
        assert resp.status_code == 200
        assert resp.data["conectores"]["total"] == 2
        assert resp.data["conectores"]["activos"] == 1
        assert resp.data["conectores"]["con_error"] == 1
        assert resp.data["conectores"]["configurando"] == 0
        assert resp.data["jobs_24h"]["total"] == 2
        assert resp.data["jobs_24h"]["completados"] == 1
        assert resp.data["jobs_24h"]["fallidos"] == 1
        assert "odoo" in resp.data["proveedores_disponibles"]

    def test_status_requiere_autenticacion(self):
        resp = APIClient().get(f"{BASE}/status/")
        assert resp.status_code in (401, 403)
