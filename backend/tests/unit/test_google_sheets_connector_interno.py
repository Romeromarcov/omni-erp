"""
Tests de la lógica interna del GoogleSheetsConnector: resolución perezosa del
cliente y la planilla, manejo de errores de autenticación/datos, e
información de versión.

El cliente real de Google nunca se invoca: se sustituye por dobles.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.integration_hub.connectors.base import (
    ConnectorConnectionError,
    ConnectorDataError,
)
from apps.integration_hub.connectors.google_sheets import connector as connector_mod
from apps.integration_hub.connectors.google_sheets.client import (
    GoogleSheetsAuthError,
    GoogleSheetsError,
)
from apps.integration_hub.connectors.google_sheets.connector import (
    GoogleSheetsConnector,
)

pytestmark = pytest.mark.unit


def _connector(config):
    instancia = MagicMock()
    instancia.get_config.return_value = config
    instancia.id_proveedor.codigo = "google_sheets"
    return GoogleSheetsConnector(instancia)


SA = {"service_account": {"client_email": "svc@p.iam.gserviceaccount.com"}}


# ── _get_client ───────────────────────────────────────────────────────────────


def test_get_client_sin_service_account_lanza_connection_error():
    conn = _connector({})
    with pytest.raises(ConnectorConnectionError, match="service_account"):
        conn._get_client()


def test_get_client_construye_y_cachea(monkeypatch):
    fake_client = MagicMock()
    construido = MagicMock(return_value=fake_client)
    monkeypatch.setattr(connector_mod, "GoogleSheetsClient", construido)
    conn = _connector({**SA, "drive_folder_id": "F9"})
    assert conn._get_client() is fake_client
    # Segunda llamada usa el cache (no reconstruye).
    assert conn._get_client() is fake_client
    construido.assert_called_once_with(
        SA["service_account"], drive_folder_id="F9"
    )


def test_get_client_auth_error_se_traduce_a_connection_error(monkeypatch):
    monkeypatch.setattr(
        connector_mod,
        "GoogleSheetsClient",
        MagicMock(side_effect=GoogleSheetsAuthError("credenciales malas")),
    )
    conn = _connector(SA)
    with pytest.raises(ConnectorConnectionError, match="credenciales malas"):
        conn._get_client()


# ── _get_spreadsheet ──────────────────────────────────────────────────────────


def test_get_spreadsheet_abre_y_persiste_id():
    conn = _connector({**SA, "titulo": "Mi Export"})
    fake_client = MagicMock()
    sh = MagicMock()
    sh.id = "SHEET_NEW"
    fake_client.abrir_o_crear_spreadsheet.return_value = sh
    conn._client = fake_client
    assert conn._get_spreadsheet() is sh
    assert conn.spreadsheet_id == "SHEET_NEW"
    fake_client.abrir_o_crear_spreadsheet.assert_called_once_with("Mi Export", "")
    # Cacheado.
    assert conn._get_spreadsheet() is sh


def test_get_spreadsheet_usa_titulo_defecto_si_no_hay():
    conn = _connector(SA)
    fake_client = MagicMock()
    fake_client.abrir_o_crear_spreadsheet.return_value = MagicMock(id="X")
    conn._client = fake_client
    conn._get_spreadsheet()
    args, _ = fake_client.abrir_o_crear_spreadsheet.call_args
    assert args[0] == connector_mod.TITULO_DEFECTO


def test_get_spreadsheet_error_de_datos_se_traduce():
    conn = _connector(SA)
    fake_client = MagicMock()
    fake_client.abrir_o_crear_spreadsheet.side_effect = GoogleSheetsError("no acceso")
    conn._client = fake_client
    with pytest.raises(ConnectorDataError, match="no acceso"):
        conn._get_spreadsheet()


# ── get_version_info / test_connection error inesperado ──────────────────────


def test_get_version_info():
    conn = _connector(SA)
    info = conn.get_version_info()
    assert info["api"] == "google-sheets-v4"
    assert info["auth"] == "service_account"


def test_test_connection_error_inesperado_no_filtra_detalle():
    conn = _connector(SA)
    with patch.object(conn, "_get_client", side_effect=RuntimeError("boom secreto")):
        res = conn.test_connection()
    assert res.success is False
    assert "boom secreto" not in res.message
    assert "RuntimeError" in res.message


# ── push_entidades: error de upsert se traduce a ConnectorDataError ──────────


def test_push_entidades_error_upsert_se_traduce_a_data_error():
    conn = _connector(SA)
    fake_client = MagicMock()
    fake_client.obtener_o_crear_worksheet.return_value = MagicMock()
    fake_client.upsert.side_effect = GoogleSheetsError("cuota excedida")
    conn._client = fake_client
    conn._spreadsheet = MagicMock()
    with pytest.raises(ConnectorDataError, match="cuota excedida"):
        conn.push_entidades("contactos", [{"id_externo": "1", "nombre": "A"}])
