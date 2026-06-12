"""
Tests de la automatización de exportación a Google Sheets (PR 3).

Cubre:
  - Task ``ejecutar_export_instancia`` (carga instancia + delega en ExportEngine,
    maneja instancia inexistente/inactiva).
  - Task periódica ``export_automatico_todos`` (solo dispara instancias Sheets
    vencidas; omite no-vencidas, otro proveedor y jobs outbound en progreso).
  - Endpoint ``exportar`` del ConectorInstanciaViewSet (202, validación de
    proveedor no-sheets → 400, aislamiento multi-tenant de empresa).

Los conectores reales (Odoo/Google) se sustituyen por dobles: nunca se llama a
Google. Celery corre EAGER (ver conftest._celery_memory_broker).
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from django.utils import timezone
from rest_framework.test import APIClient

from apps.integration_hub import tasks
from apps.integration_hub.models import (
    ConectorInstancia,
    ConectorProveedor,
    JobSincronizacion,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _proveedor(codigo, nombre):
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


def _instancia_sheets(
    empresa,
    *,
    nombre="Sheets Destino",
    intervalo=15,
    ultimo_sync=None,
    estado="activo",
    entidades=("contactos",),
):
    prov_odoo = _proveedor("odoo", "Odoo")
    prov_sheets = _proveedor("google_sheets", "Google Sheets")
    origen = ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov_odoo,
        nombre=f"{nombre} Origen",
        configuracion={"host": "https://x.odoo.com", "user": "u", "api_key": "k"},
        entidades_activas=list(entidades),
    )
    destino = ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov_sheets,
        nombre=nombre,
        estado=estado,
        intervalo_sync_minutos=intervalo,
        ultimo_sync=ultimo_sync,
        configuracion={
            "service_account": {"client_email": "svc@p.iam.gserviceaccount.com"},
            "source_instancia_id": str(origen.pk),
        },
        entidades_activas=list(entidades),
    )
    return destino


# ── Task ejecutar_export_instancia ───────────────────────────────────────────


def test_ejecutar_export_instancia_delega_en_export_engine(empresa_a):
    destino = _instancia_sheets(empresa_a)
    fake_job = MagicMock()
    fake_job.id_job = "job-uuid"
    fake_job.tipo_entidad = "contactos"
    fake_job.estado = "completado"
    fake_job.creados = 3
    fake_job.actualizados = 1
    fake_job.omitidos = 0
    fake_job.fallidos = 0

    with patch(
        "apps.integration_hub.services.export_engine.ExportEngine.exportar",
        return_value=[fake_job],
    ) as mock_exportar:
        resultado = tasks.ejecutar_export_instancia(
            str(destino.pk), ["contactos"], incremental=True
        )

    mock_exportar.assert_called_once()
    _, kwargs = mock_exportar.call_args
    assert kwargs["tipos"] == ["contactos"]
    assert kwargs["incremental"] is True
    assert resultado["instancia_id"] == str(destino.pk)
    assert resultado["jobs"][0]["tipo_entidad"] == "contactos"
    assert resultado["jobs"][0]["creados"] == 3


def test_ejecutar_export_instancia_instancia_inexistente():
    resultado = tasks.ejecutar_export_instancia(
        "00000000-0000-0000-0000-000000000000", None
    )
    assert "error" in resultado


def test_ejecutar_export_instancia_inactiva_no_exporta(empresa_a):
    destino = _instancia_sheets(empresa_a)
    destino.activo = False
    destino.save(update_fields=["activo"])

    with patch(
        "apps.integration_hub.services.export_engine.ExportEngine.exportar"
    ) as mock_exportar:
        resultado = tasks.ejecutar_export_instancia(str(destino.pk), None)

    mock_exportar.assert_not_called()
    assert "error" in resultado


# ── Task periódica export_automatico_todos ───────────────────────────────────


def test_export_automatico_dispara_instancia_sheets_vencida(empresa_a):
    # ultimo_sync hace 1h, intervalo 15 min → vencida.
    destino = _instancia_sheets(
        empresa_a, ultimo_sync=timezone.now() - timedelta(hours=1)
    )
    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resultado = tasks.export_automatico_todos()

    assert resultado == {"exports_encolados": 1}
    mock_delay.assert_called_once_with(str(destino.pk), ["contactos"], incremental=True)


def test_export_automatico_dispara_si_nunca_sincronizo(empresa_a):
    _instancia_sheets(empresa_a, ultimo_sync=None)
    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resultado = tasks.export_automatico_todos()
    assert resultado == {"exports_encolados": 1}
    mock_delay.assert_called_once()


def test_export_automatico_omite_instancia_no_vencida(empresa_a):
    # ultimo_sync hace 1 min, intervalo 15 → aún no vence.
    _instancia_sheets(empresa_a, ultimo_sync=timezone.now() - timedelta(minutes=1))
    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resultado = tasks.export_automatico_todos()
    assert resultado == {"exports_encolados": 0}
    mock_delay.assert_not_called()


def test_export_automatico_omite_proveedor_no_sheets(empresa_a):
    # Instancia Odoo con intervalo y vencida: NO debe dispararse (solo sheets).
    prov_odoo = _proveedor("odoo", "Odoo")
    ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_odoo,
        nombre="Odoo Activo",
        estado="activo",
        intervalo_sync_minutos=15,
        ultimo_sync=timezone.now() - timedelta(hours=1),
        configuracion={"host": "h", "user": "u", "api_key": "k"},
        entidades_activas=["contactos"],
    )
    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resultado = tasks.export_automatico_todos()
    assert resultado == {"exports_encolados": 0}
    mock_delay.assert_not_called()


def test_export_automatico_omite_intervalo_cero(empresa_a):
    _instancia_sheets(
        empresa_a, intervalo=0, ultimo_sync=timezone.now() - timedelta(hours=1)
    )
    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resultado = tasks.export_automatico_todos()
    assert resultado == {"exports_encolados": 0}
    mock_delay.assert_not_called()


def test_export_automatico_omite_si_job_outbound_en_progreso(empresa_a):
    destino = _instancia_sheets(
        empresa_a, ultimo_sync=timezone.now() - timedelta(hours=1)
    )
    JobSincronizacion.objects.create(
        id_instancia=destino,
        tipo_entidad="contactos",
        direccion="outbound",
        estado="en_progreso",
    )
    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resultado = tasks.export_automatico_todos()
    assert resultado == {"exports_encolados": 0}
    mock_delay.assert_not_called()


# ── Endpoint exportar ────────────────────────────────────────────────────────


def _url(instancia):
    return f"/api/integration-hub/instancias/{instancia.pk}/exportar/"


def test_endpoint_exportar_encola_y_responde_202(empresa_a, user_a):
    destino = _instancia_sheets(empresa_a)
    client = APIClient()
    client.force_authenticate(user=user_a)

    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-123")
        resp = client.post(
            _url(destino), {"tipos": ["contactos"], "full": True}, format="json"
        )

    assert resp.status_code == 202
    assert resp.data["task_id"] == "task-123"
    assert "mensaje" in resp.data
    mock_delay.assert_called_once_with(
        str(destino.pk), ["contactos"], incremental=False
    )


def test_endpoint_exportar_default_incremental_true(empresa_a, user_a):
    destino = _instancia_sheets(empresa_a)
    client = APIClient()
    client.force_authenticate(user=user_a)

    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="t")
        resp = client.post(_url(destino), {}, format="json")

    assert resp.status_code == 202
    # Sin 'full' ni 'tipos' → tipos=None, incremental=True.
    mock_delay.assert_called_once_with(str(destino.pk), None, incremental=True)


def test_endpoint_exportar_proveedor_no_sheets_400(empresa_a, user_a):
    prov_odoo = _proveedor("odoo", "Odoo")
    instancia = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_odoo,
        nombre="Odoo No Sheets",
        estado="activo",
        configuracion={"host": "h", "user": "u", "api_key": "k"},
        entidades_activas=["contactos"],
    )
    client = APIClient()
    client.force_authenticate(user=user_a)

    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resp = client.post(_url(instancia), {}, format="json")

    assert resp.status_code == 400
    assert "google_sheets" in resp.data["error"]
    mock_delay.assert_not_called()


def test_endpoint_exportar_aislamiento_empresa(empresa_a, user_b):
    # Instancia de empresa_a, usuario de empresa_b → no la ve (404).
    destino = _instancia_sheets(empresa_a)
    client = APIClient()
    client.force_authenticate(user=user_b)

    with patch.object(tasks.ejecutar_export_instancia, "delay") as mock_delay:
        resp = client.post(_url(destino), {}, format="json")

    assert resp.status_code == 404
    mock_delay.assert_not_called()


# ── Alta de instancias por API (validación por proveedor) ────────────────────


def _crear_instancia_api(user, payload):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.post("/api/integration-hub/instancias/", payload, format="json")


def test_crear_instancia_sheets_por_api(empresa_a, user_a):
    """El alta de google_sheets no exige host/user/api_key (usa service account)."""
    prov_odoo = _proveedor("odoo", "Odoo")
    prov_sheets = _proveedor("google_sheets", "Google Sheets")
    origen = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_odoo,
        nombre="Odoo Origen API",
        configuracion={"host": "h", "user": "u", "api_key": "k"},
    )
    resp = _crear_instancia_api(
        user_a,
        {
            "id_proveedor": str(prov_sheets.pk),
            "nombre": "Sheets vía API",
            "configuracion": {
                "service_account": {"client_email": "svc@p.iam.gserviceaccount.com"},
                "source_instancia_id": str(origen.pk),
            },
            "entidades_activas": ["contactos"],
        },
    )
    assert resp.status_code == 201, resp.data


def test_crear_instancia_sheets_sin_service_account_400(empresa_a, user_a):
    prov_sheets = _proveedor("google_sheets", "Google Sheets")
    resp = _crear_instancia_api(
        user_a,
        {
            "id_proveedor": str(prov_sheets.pk),
            "nombre": "Sheets sin SA",
            "configuracion": {"source_instancia_id": "algo"},
        },
    )
    assert resp.status_code == 400
    assert "service_account" in str(resp.data)


def test_crear_instancia_sheets_sin_origen_400(empresa_a, user_a):
    prov_sheets = _proveedor("google_sheets", "Google Sheets")
    resp = _crear_instancia_api(
        user_a,
        {
            "id_proveedor": str(prov_sheets.pk),
            "nombre": "Sheets sin origen",
            "configuracion": {
                "service_account": {"client_email": "svc@p.iam.gserviceaccount.com"}
            },
        },
    )
    assert resp.status_code == 400
    assert "source_instancia_id" in str(resp.data)


def test_crear_instancia_odoo_sigue_exigiendo_credenciales(empresa_a, user_a):
    """La validación clásica (host/user/api_key) se mantiene para otros proveedores."""
    prov_odoo = _proveedor("odoo", "Odoo")
    resp = _crear_instancia_api(
        user_a,
        {
            "id_proveedor": str(prov_odoo.pk),
            "nombre": "Odoo incompleto",
            "configuracion": {"host": "https://x.odoo.com"},
        },
    )
    assert resp.status_code == 400
    assert "user" in str(resp.data)
