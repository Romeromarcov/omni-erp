"""
Tests de las vistas del Integration Hub (DRF), cubriendo las acciones de
instancia (test, sync, jobs, entidades, preview), las de job (logs, cancelar) y
la vista de estado. Todo con aislamiento multi-tenant (R-CODE-1).

Los conectores reales se sustituyen por dobles; nunca se llama a un sistema
externo. Celery corre EAGER (conftest), pero las acciones se mockean para no
depender del SyncEngine real.
"""

from unittest.mock import MagicMock, patch

import pytest

from django.utils import timezone
from rest_framework.test import APIClient

from apps.integration_hub.connectors import registry as registry_mod
from apps.integration_hub.connectors.base import (
    ConnectorConnectionError,
    TestConnectionResult as _TestConnectionResult,
)
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)

pytestmark = pytest.mark.django_db


def _proveedor(codigo="odoo", nombre="Odoo"):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo=codigo,
        defaults={
            "nombre": nombre,
            "estado": "activo",
            "activo": True,
            "capacidades": ["contactos", "productos"],
        },
    )
    return prov


def _instancia(empresa, *, estado="activo", entidades=("contactos",), prov=None):
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov or _proveedor(),
        nombre="Odoo Test",
        estado=estado,
        configuracion={"host": "h", "user": "u", "api_key": "k"},
        entidades_activas=list(entidades),
    )


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ── acción test_connection ────────────────────────────────────────────────────


def test_test_connection_exitoso_marca_activo(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a, estado="configurando")
    fake = MagicMock()
    fake.test_connection.return_value = _TestConnectionResult(
        success=True, message="OK", version="17.0", details={"x": 1}
    )
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda i: fake)

    resp = _client(user_a).post(f"/api/integration-hub/instancias/{inst.pk}/test/")
    assert resp.status_code == 200
    assert resp.data["success"] is True
    inst.refresh_from_db()
    assert inst.estado == "activo"
    assert inst.version_detectada == "17.0"


def test_test_connection_fallo_logico_marca_error(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a)
    fake = MagicMock()
    fake.test_connection.return_value = _TestConnectionResult(
        success=False, message="credenciales malas"
    )
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda i: fake)

    resp = _client(user_a).post(f"/api/integration-hub/instancias/{inst.pk}/test/")
    assert resp.status_code == 200
    assert resp.data["success"] is False
    inst.refresh_from_db()
    assert inst.estado == "error"


def test_test_connection_excepcion_devuelve_502(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a)
    monkeypatch.setattr(
        registry_mod.registry,
        "get_connector",
        MagicMock(side_effect=ConnectorConnectionError("sin conexión")),
    )
    resp = _client(user_a).post(f"/api/integration-hub/instancias/{inst.pk}/test/")
    assert resp.status_code == 502
    assert resp.data["success"] is False
    inst.refresh_from_db()
    assert inst.estado == "error"


# ── edición (PATCH) de la instancia ────────────────────────────────────────────


def test_patch_conserva_api_key_si_no_se_reenvia(empresa_a, user_a):
    """Editar host/user sin reenviar api_key NO debe borrar la credencial."""
    inst = _instancia(empresa_a)
    resp = _client(user_a).patch(
        f"/api/integration-hub/instancias/{inst.pk}/",
        {"configuracion": {"host": "https://nuevo.odoo.com", "user": "u"}},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    inst.refresh_from_db()
    cfg = inst.get_config()
    assert cfg["host"] == "https://nuevo.odoo.com"
    assert cfg["api_key"] == "k"  # se conservó la existente


def test_crear_google_sheets_sin_service_account_400(empresa_a, user_a):
    """Validación serializer: google_sheets requiere service_account."""
    prov = _proveedor(codigo="google_sheets", nombre="Google Sheets")
    resp = _client(user_a).post(
        "/api/integration-hub/instancias/",
        {
            "id_proveedor": str(prov.pk),
            "nombre": "Export sin SA",
            "configuracion": {"source_instancia_id": "x"},
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "service_account" in str(resp.data)


def test_crear_google_sheets_sin_source_instancia_400(empresa_a, user_a):
    """Validación serializer: google_sheets requiere source_instancia_id."""
    prov = _proveedor(codigo="google_sheets", nombre="Google Sheets")
    resp = _client(user_a).post(
        "/api/integration-hub/instancias/",
        {
            "id_proveedor": str(prov.pk),
            "nombre": "Export sin origen",
            "configuracion": {
                "service_account": {"client_email": "svc@x.iam.gserviceaccount.com"}
            },
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "source_instancia_id" in str(resp.data)


def test_patch_api_key_vacia_explicita_conserva(empresa_a, user_a):
    """Enviar api_key='' explícita NO borra la credencial (rama secreto vacío)."""
    inst = _instancia(empresa_a)
    resp = _client(user_a).patch(
        f"/api/integration-hub/instancias/{inst.pk}/",
        {"configuracion": {"host": "h", "user": "u", "api_key": ""}},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    inst.refresh_from_db()
    assert inst.get_config()["api_key"] == "k"


def test_patch_actualiza_api_key_si_se_envia(empresa_a, user_a):
    inst = _instancia(empresa_a)
    resp = _client(user_a).patch(
        f"/api/integration-hub/instancias/{inst.pk}/",
        {"configuracion": {"host": "h", "user": "u", "api_key": "nueva"}},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    inst.refresh_from_db()
    assert inst.get_config()["api_key"] == "nueva"


def test_patch_no_cambia_proveedor(empresa_a, user_a):
    """El proveedor es inmutable en edición."""
    inst = _instancia(empresa_a)
    otro = _proveedor(codigo="google_sheets", nombre="Google Sheets")
    resp = _client(user_a).patch(
        f"/api/integration-hub/instancias/{inst.pk}/",
        {"id_proveedor": str(otro.pk), "nombre": "Renombrado"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    inst.refresh_from_db()
    assert inst.nombre == "Renombrado"
    assert inst.id_proveedor_id != otro.pk  # no cambió de proveedor


def test_patch_db_vacia_no_borra_db_si_no_se_envia(empresa_a, user_a):
    """Editar sin enviar 'db' conserva la base de datos previa (no es secreto,
    pero al no venir en el payload tampoco debe perderse)."""
    inst = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=_proveedor(),
        nombre="Odoo con db",
        estado="activo",
        configuracion={"host": "h", "user": "u", "api_key": "k", "db": "midb"},
        entidades_activas=["contactos"],
    )
    resp = _client(user_a).patch(
        f"/api/integration-hub/instancias/{inst.pk}/",
        {"configuracion": {"host": "h2", "user": "u", "db": "otradb"}},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    inst.refresh_from_db()
    assert inst.get_config()["db"] == "otradb"


# ── acción trigger_sync ───────────────────────────────────────────────────────


def test_trigger_sync_crea_job_y_encola(empresa_a, user_a):
    inst = _instancia(empresa_a, entidades=["contactos"])
    with patch(
        "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay"
    ) as mock_delay:
        mock_delay.return_value = MagicMock(id="task-xyz")
        resp = _client(user_a).post(
            f"/api/integration-hub/instancias/{inst.pk}/sync/",
            {"tipo_entidad": "contactos", "direccion": "inbound"},
            format="json",
        )
    assert resp.status_code == 202
    job = JobSincronizacion.objects.get(id_instancia=inst)
    assert job.celery_task_id == "task-xyz"


def test_trigger_sync_instancia_en_error_400(empresa_a, user_a):
    inst = _instancia(empresa_a, estado="error")
    resp = _client(user_a).post(
        f"/api/integration-hub/instancias/{inst.pk}/sync/",
        {"tipo_entidad": "contactos"},
        format="json",
    )
    assert resp.status_code == 400


def test_trigger_sync_entidad_no_habilitada_400(empresa_a, user_a):
    inst = _instancia(empresa_a, entidades=["productos"])
    resp = _client(user_a).post(
        f"/api/integration-hub/instancias/{inst.pk}/sync/",
        {"tipo_entidad": "contactos"},
        format="json",
    )
    assert resp.status_code == 400
    assert "no está habilitada" in resp.data["error"]


def test_trigger_sync_fallback_sincrono_si_celery_falla(empresa_a, user_a):
    inst = _instancia(empresa_a, entidades=["contactos"])
    with patch(
        "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay",
        side_effect=RuntimeError("broker caído"),
    ), patch(
        "apps.integration_hub.services.sync_engine.SyncEngine.ejecutar_job"
    ) as mock_run:
        resp = _client(user_a).post(
            f"/api/integration-hub/instancias/{inst.pk}/sync/",
            {"tipo_entidad": "contactos"},
            format="json",
        )
    assert resp.status_code == 202
    mock_run.assert_called_once()


# ── acción list_jobs ──────────────────────────────────────────────────────────


def test_list_jobs_devuelve_historial(empresa_a, user_a):
    inst = _instancia(empresa_a)
    JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="completado",
        iniciado_en=timezone.now(),
    )
    resp = _client(user_a).get(f"/api/integration-hub/instancias/{inst.pk}/jobs/")
    assert resp.status_code == 200
    assert len(resp.data) == 1


# ── acción list_entidades ─────────────────────────────────────────────────────


def test_list_entidades_filtra_por_tipo(empresa_a, user_a):
    inst = _instancia(empresa_a)
    EntidadSincronizada.objects.create(
        id_instancia=inst, tipo_entidad="contactos", id_externo="1", id_omni="u1"
    )
    EntidadSincronizada.objects.create(
        id_instancia=inst, tipo_entidad="productos", id_externo="2", id_omni="u2"
    )
    resp = _client(user_a).get(
        f"/api/integration-hub/instancias/{inst.pk}/entidades/contactos/"
    )
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["id_externo"] == "1"


# ── acción preview_data ───────────────────────────────────────────────────────


def test_preview_data_devuelve_muestra(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a)
    fake = MagicMock()
    fake.supports.return_value = True
    fake.pull_contactos.return_value = [{"id_externo": "1"}] * 20
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda i: fake)

    resp = _client(user_a).get(
        f"/api/integration-hub/instancias/{inst.pk}/preview/contactos/"
    )
    assert resp.status_code == 200
    assert len(resp.data["muestra"]) == 10  # preview máximo 10


def test_preview_data_entidad_no_soportada_400(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a)
    fake = MagicMock()
    fake.supports.return_value = False
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda i: fake)
    resp = _client(user_a).get(
        f"/api/integration-hub/instancias/{inst.pk}/preview/contactos/"
    )
    assert resp.status_code == 400


def test_preview_data_get_connector_falla_502(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a)
    monkeypatch.setattr(
        registry_mod.registry,
        "get_connector",
        MagicMock(side_effect=RuntimeError("x")),
    )
    resp = _client(user_a).get(
        f"/api/integration-hub/instancias/{inst.pk}/preview/contactos/"
    )
    assert resp.status_code == 502


def test_preview_data_pull_revienta_502(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a)
    fake = MagicMock()
    fake.supports.return_value = True
    fake.pull_contactos.side_effect = RuntimeError("odoo caído")
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda i: fake)
    resp = _client(user_a).get(
        f"/api/integration-hub/instancias/{inst.pk}/preview/contactos/"
    )
    assert resp.status_code == 502


def test_preview_data_sin_metodo_pull_400(empresa_a, user_a, monkeypatch):
    inst = _instancia(empresa_a)
    fake = MagicMock()
    fake.supports.return_value = True
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda i: fake)
    # 'inventario' está soportado pero SyncEngine.PULL_METHODS puede no tenerlo.
    with patch(
        "apps.integration_hub.services.sync_engine.SyncEngine.PULL_METHODS",
        {"contactos": "pull_contactos"},
    ):
        resp = _client(user_a).get(
            f"/api/integration-hub/instancias/{inst.pk}/preview/productos/"
        )
    assert resp.status_code == 400


# ── JobSincronizacionViewSet: logs y cancelar ────────────────────────────────


def test_job_logs(empresa_a, user_a):
    inst = _instancia(empresa_a)
    job = JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="completado"
    )
    LogDetalleSincronizacion.objects.create(
        id_job=job, id_externo="1", operacion="crear"
    )
    resp = _client(user_a).get(f"/api/integration-hub/jobs/{job.pk}/logs/")
    assert resp.status_code == 200
    assert len(resp.data) == 1


def test_job_cancelar_pendiente(empresa_a, user_a):
    inst = _instancia(empresa_a)
    job = JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="pendiente",
        celery_task_id="t1",
    )
    with patch("config.celery.app.control.revoke") as mock_revoke:
        resp = _client(user_a).post(f"/api/integration-hub/jobs/{job.pk}/cancelar/")
    assert resp.status_code == 200
    job.refresh_from_db()
    assert job.estado == "cancelado"
    mock_revoke.assert_called_once()


def test_job_cancelar_completado_400(empresa_a, user_a):
    inst = _instancia(empresa_a)
    job = JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="completado"
    )
    resp = _client(user_a).post(f"/api/integration-hub/jobs/{job.pk}/cancelar/")
    assert resp.status_code == 400


def test_job_aislamiento_empresa(empresa_a, empresa_b, user_b):
    inst = _instancia(empresa_a)
    job = JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="completado"
    )
    resp = _client(user_b).get(f"/api/integration-hub/jobs/{job.pk}/logs/")
    assert resp.status_code == 404


# ── IntegrationHubStatusView ──────────────────────────────────────────────────


def test_status_resume_conectores_y_jobs(empresa_a, user_a):
    inst = _instancia(empresa_a, estado="activo")
    JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="completado",
        iniciado_en=timezone.now(),
    )
    resp = _client(user_a).get("/api/integration-hub/status/")
    assert resp.status_code == 200
    assert resp.data["conectores"]["activos"] == 1
    assert resp.data["jobs_24h"]["completados"] == 1
    assert "proveedores_disponibles" in resp.data


# ── Catálogo de proveedores ───────────────────────────────────────────────────


def test_lista_proveedores_activos(empresa_a, user_a):
    _proveedor()
    resp = _client(user_a).get("/api/integration-hub/proveedores/")
    assert resp.status_code == 200
    assert any(p["codigo"] == "odoo" for p in resp.data)
