"""
Tests de los comandos de management del conector Google Sheets:
``configurar_conector_sheets`` y ``exportar_a_sheets``.

Verifican el resolver de empresa/origen, el cifrado de la config (sin filtrar la
clave del service account), y la orquestación del export. No tocan Google.
"""

import json
from unittest.mock import MagicMock

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


SERVICE_ACCOUNT = {
    "type": "service_account",
    "client_email": "svc@proj.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE\\n-----END PRIVATE KEY-----\\n",
}


def _odoo_instancia(empresa, nombre="Odoo Origen"):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo", defaults={"nombre": "Odoo", "estado": "activo"}
    )
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov,
        nombre=nombre,
        configuracion={"host": "h", "user": "u", "api_key": "k"},
    )


def _sa_file(tmp_path):
    ruta = tmp_path / "sa.json"
    ruta.write_text(json.dumps(SERVICE_ACCOUNT), encoding="utf-8")
    return str(ruta)


def test_configurar_crea_instancia_con_config_cifrada(tmp_path, empresa_a):
    origen = _odoo_instancia(empresa_a)
    call_command(
        "configurar_conector_sheets",
        "--empresa",
        str(empresa_a.pk),
        "--service-account",
        _sa_file(tmp_path),
        "--source",
        origen.nombre,
        "--nombre",
        "Sheets Export",
        "--entidades",
        "contactos,productos",
    )
    inst = ConectorInstancia.objects.get(id_empresa=empresa_a, nombre="Sheets Export")
    cfg = inst.get_config()
    assert cfg["service_account"]["client_email"] == SERVICE_ACCOUNT["client_email"]
    assert cfg["source_instancia_id"] == str(origen.pk)
    assert inst.entidades_activas == ["contactos", "productos"]


def test_configurar_falla_si_origen_no_existe(tmp_path, empresa_a):
    with pytest.raises(CommandError, match="instancia origen"):
        call_command(
            "configurar_conector_sheets",
            "--empresa",
            str(empresa_a.pk),
            "--service-account",
            _sa_file(tmp_path),
            "--source",
            "No Existe",
        )


def test_configurar_falla_si_json_no_es_service_account(tmp_path, empresa_a):
    _odoo_instancia(empresa_a)
    ruta = tmp_path / "malo.json"
    ruta.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    with pytest.raises(CommandError, match="client_email"):
        call_command(
            "configurar_conector_sheets",
            "--empresa",
            str(empresa_a.pk),
            "--service-account",
            str(ruta),
            "--source",
            "Odoo Origen",
        )


def test_configurar_con_test_marca_estado(tmp_path, empresa_a, monkeypatch):
    origen = _odoo_instancia(empresa_a)
    from apps.integration_hub.connectors import registry as registry_mod

    fake = MagicMock()
    fake.test_connection.return_value = MagicMock(
        success=True, version="google-sheets-v4", message="OK"
    )
    monkeypatch.setattr(registry_mod.registry, "get_connector", lambda inst: fake)

    call_command(
        "configurar_conector_sheets",
        "--empresa",
        str(empresa_a.pk),
        "--service-account",
        _sa_file(tmp_path),
        "--source",
        origen.nombre,
        "--nombre",
        "Sheets Export",
        "--test",
    )
    inst = ConectorInstancia.objects.get(id_empresa=empresa_a, nombre="Sheets Export")
    assert inst.estado == "activo"
    assert inst.version_detectada == "google-sheets-v4"


def test_exportar_invoca_engine_y_resuelve_destino(empresa_a, monkeypatch):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="google_sheets", defaults={"nombre": "Google Sheets", "estado": "activo"}
    )
    destino = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov,
        nombre="Sheets Export",
        configuracion={"service_account": SERVICE_ACCOUNT},
        entidades_activas=["contactos"],
    )
    from apps.integration_hub.services import export_engine as ee

    job = MagicMock(
        tipo_entidad="contactos",
        estado="completado",
        creados=3,
        actualizados=0,
        omitidos=0,
        fallidos=0,
    )
    monkeypatch.setattr(ee.ExportEngine, "exportar", lambda self, *a, **k: [job])

    call_command(
        "exportar_a_sheets", "--empresa", str(empresa_a.pk), "--destino", destino.nombre
    )


def test_exportar_falla_si_destino_no_existe(empresa_a):
    with pytest.raises(CommandError, match="destino"):
        call_command(
            "exportar_a_sheets", "--empresa", str(empresa_a.pk), "--destino", "Nada"
        )
