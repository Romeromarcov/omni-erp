"""
Tests de borde que completan la cobertura del Integration Hub:
serializers (validación de configuracion, nombre de quien inicia el job),
ramas de error de los comandos de management y del ExportEngine.
"""

import json
from unittest.mock import MagicMock

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.integration_hub.connectors.base import SyncResult
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor
from apps.integration_hub.serializers import (
    ConectorInstanciaCreateSerializer,
    JobSincronizacionSerializer,
)
from apps.integration_hub.services.export_engine import ExportEngine
from apps.integration_hub.services import export_engine as export_engine_mod

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

SERVICE_ACCOUNT = {
    "type": "service_account",
    "client_email": "svc@proj.iam.gserviceaccount.com",
}


def _odoo(empresa, nombre="Odoo Origen"):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo", defaults={"nombre": "Odoo", "estado": "activo"}
    )
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov,
        nombre=nombre,
        configuracion={"host": "h", "user": "u", "api_key": "k"},
    )


# ── Serializers ───────────────────────────────────────────────────────────────


def test_validate_configuracion_no_dict_falla():
    ser = ConectorInstanciaCreateSerializer()
    from rest_framework import serializers as drf

    with pytest.raises(drf.ValidationError):
        ser.validate_configuracion(["no", "es", "dict"])


def test_validate_sin_configuracion_es_patch_parcial():
    # configuracion ausente (PATCH parcial) → validate() no exige nada.
    ser = ConectorInstanciaCreateSerializer()
    assert ser.validate({"nombre": "X"}) == {"nombre": "X"}


def test_job_serializer_iniciado_por_automatico(empresa_a):
    from apps.integration_hub.models import JobSincronizacion

    inst = _odoo(empresa_a)
    job = JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="completado",
        iniciado_por=None,
    )
    data = JobSincronizacionSerializer(job).data
    assert data["iniciado_por_nombre"] == "Automático"


def test_job_serializer_iniciado_por_usuario(empresa_a, user_a):
    from apps.integration_hub.models import JobSincronizacion

    inst = _odoo(empresa_a)
    job = JobSincronizacion.objects.create(
        id_instancia=inst, tipo_entidad="contactos", estado="completado",
        iniciado_por=user_a,
    )
    data = JobSincronizacionSerializer(job).data
    assert data["iniciado_por_nombre"]  # nombre no vacío


# ── Comando configurar_conector_sheets: ramas de error ───────────────────────


def _sa_file(tmp_path):
    ruta = tmp_path / "sa.json"
    ruta.write_text(json.dumps(SERVICE_ACCOUNT), encoding="utf-8")
    return str(ruta)


def test_configurar_resuelve_empresa_por_rif(tmp_path, empresa_a):
    origen = _odoo(empresa_a)
    call_command(
        "configurar_conector_sheets",
        "--empresa", empresa_a.identificador_fiscal,  # por RIF, no UUID
        "--service-account", _sa_file(tmp_path),
        "--source", origen.nombre,
        "--nombre", "Sheets RIF",
    )
    assert ConectorInstancia.objects.filter(
        id_empresa=empresa_a, nombre="Sheets RIF"
    ).exists()


def test_configurar_empresa_inexistente_falla(tmp_path):
    with pytest.raises(CommandError, match="empresa"):
        call_command(
            "configurar_conector_sheets",
            "--empresa", "no-existe-rif",
            "--service-account", _sa_file(tmp_path),
            "--source", "x",
        )


def test_configurar_service_account_inexistente_falla(empresa_a):
    _odoo(empresa_a)
    with pytest.raises(CommandError, match="service account"):
        call_command(
            "configurar_conector_sheets",
            "--empresa", str(empresa_a.pk),
            "--service-account", "/ruta/que/no/existe.json",
            "--source", "Odoo Origen",
        )


def test_configurar_service_account_json_invalido_falla(tmp_path, empresa_a):
    _odoo(empresa_a)
    ruta = tmp_path / "malo.json"
    ruta.write_text("{ no es json", encoding="utf-8")
    with pytest.raises(CommandError, match="No se pudo leer"):
        call_command(
            "configurar_conector_sheets",
            "--empresa", str(empresa_a.pk),
            "--service-account", str(ruta),
            "--source", "Odoo Origen",
        )


def test_configurar_resuelve_origen_por_id(tmp_path, empresa_a):
    origen = _odoo(empresa_a)
    call_command(
        "configurar_conector_sheets",
        "--empresa", str(empresa_a.pk),
        "--service-account", _sa_file(tmp_path),
        "--source", str(origen.pk),  # por UUID
        "--nombre", "Sheets por ID origen",
    )
    inst = ConectorInstancia.objects.get(
        id_empresa=empresa_a, nombre="Sheets por ID origen"
    )
    assert inst.get_config()["source_instancia_id"] == str(origen.pk)


def test_configurar_test_fallido_marca_error(tmp_path, empresa_a, monkeypatch):
    origen = _odoo(empresa_a)
    from apps.integration_hub.connectors import registry as registry_mod

    fake = MagicMock()
    fake.test_connection.return_value = MagicMock(success=False, message="no conecta")
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda i: fake)

    call_command(
        "configurar_conector_sheets",
        "--empresa", str(empresa_a.pk),
        "--service-account", _sa_file(tmp_path),
        "--source", origen.nombre,
        "--nombre", "Sheets Test Fail",
        "--test",
    )
    inst = ConectorInstancia.objects.get(
        id_empresa=empresa_a, nombre="Sheets Test Fail"
    )
    assert inst.estado == "error"


# ── Comando exportar_a_sheets: ramas de error ────────────────────────────────


def _sheets_destino(empresa, origen):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="google_sheets", defaults={"nombre": "Google Sheets", "estado": "activo"}
    )
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov,
        nombre="Sheets Destino",
        configuracion={
            "service_account": SERVICE_ACCOUNT,
            "source_instancia_id": str(origen.pk),
        },
        entidades_activas=["contactos"],
    )


def test_exportar_empresa_por_rif(empresa_a, monkeypatch):
    origen = _odoo(empresa_a)
    destino = _sheets_destino(empresa_a, origen)
    job = MagicMock(
        tipo_entidad="contactos", estado="completado",
        creados=1, actualizados=0, omitidos=0, fallidos=0,
    )
    monkeypatch.setattr(ExportEngine, "exportar", lambda self, *a, **k: [job])
    call_command(
        "exportar_a_sheets",
        "--empresa", empresa_a.identificador_fiscal,
        "--destino", destino.nombre,
    )


def test_exportar_empresa_inexistente_falla():
    with pytest.raises(CommandError, match="empresa"):
        call_command(
            "exportar_a_sheets", "--empresa", "no-existe", "--destino", "x"
        )


def test_exportar_connector_error_se_traduce_a_command_error(empresa_a, monkeypatch):
    origen = _odoo(empresa_a)
    destino = _sheets_destino(empresa_a, origen)
    from apps.integration_hub.connectors.base import ConnectorError

    def _boom(self, *a, **k):
        raise ConnectorError("origen mal configurado")

    monkeypatch.setattr(ExportEngine, "exportar", _boom)
    with pytest.raises(CommandError, match="origen mal configurado"):
        call_command(
            "exportar_a_sheets",
            "--empresa", str(empresa_a.pk),
            "--destino", destino.nombre,
        )


def test_exportar_job_fallido_usa_estilo_error(empresa_a, monkeypatch):
    origen = _odoo(empresa_a)
    destino = _sheets_destino(empresa_a, origen)
    job = MagicMock(
        tipo_entidad="contactos", estado="fallido",
        creados=0, actualizados=0, omitidos=0, fallidos=1,
    )
    monkeypatch.setattr(ExportEngine, "exportar", lambda self, *a, **k: [job])
    call_command(
        "exportar_a_sheets",
        "--empresa", str(empresa_a.pk),
        "--destino", destino.nombre,
    )


# ── ExportEngine: ramas de entidad no soportada ──────────────────────────────


def _instancias(empresa):
    prov_odoo, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo", defaults={"nombre": "Odoo", "estado": "activo"}
    )
    prov_sheets, _ = ConectorProveedor.objects.get_or_create(
        codigo="google_sheets",
        defaults={"nombre": "Google Sheets", "estado": "activo"},
    )
    origen = ConectorInstancia.objects.create(
        id_empresa=empresa, id_proveedor=prov_odoo, nombre="Odoo Origen ee",
        configuracion={"host": "h", "user": "u", "api_key": "k"},
    )
    destino = ConectorInstancia.objects.create(
        id_empresa=empresa, id_proveedor=prov_sheets, nombre="Sheets Destino ee",
        configuracion={
            "service_account": {"client_email": "svc@p.iam.gserviceaccount.com"},
            "source_instancia_id": str(origen.pk),
        },
        entidades_activas=["contactos"],
    )
    return origen, destino


def test_export_tipo_sin_metodo_pull_marca_job_fallido(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a)
    fake_origen = MagicMock(spec=[])  # sin métodos pull_*
    fake_destino = MagicMock()
    monkeypatch.setattr(
        export_engine_mod.registry,
        "get_connector",
        lambda inst: fake_destino if inst.id_proveedor.codigo == "google_sheets"
        else fake_origen,
    )
    jobs = ExportEngine().exportar(destino, tipos=["contactos"])
    assert jobs[0].estado == "fallido"
    assert "no sabe leer" in jobs[0].resumen_errores[0]["error"]


def test_export_destino_no_soporta_entidad_marca_fallido(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a)
    fake_origen = MagicMock()
    fake_origen.pull_contactos.return_value = []
    fake_destino = MagicMock()
    fake_destino.supports.return_value = False
    monkeypatch.setattr(
        export_engine_mod.registry,
        "get_connector",
        lambda inst: fake_destino if inst.id_proveedor.codigo == "google_sheets"
        else fake_origen,
    )
    jobs = ExportEngine().exportar(destino, tipos=["contactos"])
    assert jobs[0].estado == "fallido"
    assert "no soporta" in jobs[0].resumen_errores[0]["error"]


def test_export_incremental_calcula_desde_del_ultimo_job(monkeypatch, empresa_a):
    from django.utils import timezone as tz
    from apps.integration_hub.models import JobSincronizacion

    origen, destino = _instancias(empresa_a)
    # Job previo completado → su completado_en se usa como 'desde'.
    previo_ts = tz.now()
    JobSincronizacion.objects.create(
        id_instancia=destino, tipo_entidad="contactos", direccion="outbound",
        estado="completado", completado_en=previo_ts,
    )
    fake_origen = MagicMock()
    fake_origen.pull_contactos.return_value = [{"id_externo": "1"}]
    fake_destino = MagicMock()
    fake_destino.supports.return_value = True
    fake_destino.push_entidades.return_value = SyncResult(
        tipo_entidad="contactos", total=1, creados=1
    )
    fake_destino.spreadsheet_id = "S"
    monkeypatch.setattr(
        export_engine_mod.registry,
        "get_connector",
        lambda inst: fake_destino if inst.id_proveedor.codigo == "google_sheets"
        else fake_origen,
    )
    ExportEngine().exportar(destino, tipos=["contactos"], incremental=True)
    _, kwargs = fake_origen.pull_contactos.call_args
    assert kwargs["desde"] == previo_ts
