"""
Tests adicionales de borde para apretar la cobertura del diff:
BaseConnector.push_entidades por defecto, fallthroughs de columns,
upsert con encabezado cambiado, y origen inexistente en ExportEngine.
"""

from unittest.mock import MagicMock

import pytest

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorError,
    ConnectorNotSupportedError,
)
from apps.integration_hub.connectors.google_sheets import columns
from apps.integration_hub.connectors.google_sheets.client import GoogleSheetsClient
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor
from apps.integration_hub.services.export_engine import ExportEngine
from apps.integration_hub.services import export_engine as export_engine_mod


class _DummyConnector(BaseConnector):
    PROVIDER_CODE = "dummy"
    PROVIDER_NAME = "Dummy"

    def test_connection(self):  # pragma: no cover - no se ejerce aquí
        return None

    def get_version_info(self):  # pragma: no cover
        return {}


def test_base_push_entidades_no_soportado_por_defecto():
    inst = MagicMock()
    inst.get_config.return_value = {}
    conn = _DummyConnector(inst)
    with pytest.raises(ConnectorNotSupportedError):
        conn.push_entidades("contactos", [])


def test_cell_valor_numerico_no_decimal_se_devuelve_tal_cual():
    # int/float (no Decimal, no bool) caen en el return final de _cell.
    assert columns._cell(42) == 42
    assert columns._cell(3.5) == 3.5


def test_indice_clave_fallback_cero_si_no_hay_columna_clave(monkeypatch):
    # Entidad cuyo primer campo no es la columna clave → fallback a 0.
    monkeypatch.setitem(
        columns.COLUMNAS, "_fake", [("otro", "Otro"), ("mas", "Más")]
    )
    assert columns.indice_clave("_fake") == 0


def test_upsert_reescribe_encabezado_si_cambio():
    client = GoogleSheetsClient.__new__(GoogleSheetsClient)
    ws = MagicMock()
    # Encabezado existente distinto del nuevo → se reescribe A1.
    ws.get_all_values.return_value = [["ID", "Viejo"], ["1", "A"]]
    creados, act, omit = client.upsert(
        ws, ["ID Externo", "Nombre"], [["1", "A2"]], key_index=0
    )
    ws.batch_update.assert_called_once()
    args, _ = ws.batch_update.call_args
    rangos = [u["range"] for u in args[0]]
    assert "A1" in rangos  # encabezado actualizado


@pytest.mark.django_db
def test_exportar_origen_inexistente_lanza(monkeypatch, empresa_a):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="google_sheets",
        defaults={"nombre": "Google Sheets", "estado": "activo"},
    )
    destino = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov,
        nombre="Sheets sin origen real",
        configuracion={
            "service_account": {"client_email": "x@y.iam.gserviceaccount.com"},
            "source_instancia_id": "00000000-0000-0000-0000-000000000000",
        },
        entidades_activas=["contactos"],
    )
    monkeypatch.setattr(
        export_engine_mod.registry, "get_connector", lambda inst: MagicMock()
    )
    with pytest.raises(ConnectorError, match="no existe"):
        ExportEngine().exportar(destino, tipos=["contactos"])
