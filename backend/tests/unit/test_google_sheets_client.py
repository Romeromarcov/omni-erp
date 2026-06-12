"""
Tests del GoogleSheetsClient (autorización, apertura/creación de planillas y
pestañas, y test de conectividad).

Nunca tocan la API real de Google: ``gspread`` y ``google-auth`` se sustituyen
por dobles vía monkeypatch sobre ``sys.modules`` (importación perezosa). El
service account es ficticio (R-CODE-8: ninguna clave real).
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

from apps.integration_hub.connectors.google_sheets.client import (
    GoogleSheetsAuthError,
    GoogleSheetsClient,
    GoogleSheetsError,
)

pytestmark = pytest.mark.unit

SERVICE_ACCOUNT = {"client_email": "svc@proj.iam.gserviceaccount.com"}


def _fake_gspread_module():
    """Módulo gspread ficticio con las excepciones que usa el cliente."""
    mod = types.ModuleType("gspread")

    class SpreadsheetNotFound(Exception):
        pass

    class WorksheetNotFound(Exception):
        pass

    mod.SpreadsheetNotFound = SpreadsheetNotFound
    mod.WorksheetNotFound = WorksheetNotFound
    mod.authorize = MagicMock()
    return mod


def _fake_google_auth_modules(creds_obj=None):
    """Crea el paquete google.oauth2.service_account con Credentials ficticias."""
    google = types.ModuleType("google")
    oauth2 = types.ModuleType("google.oauth2")
    sa_mod = types.ModuleType("google.oauth2.service_account")

    class Credentials:
        @staticmethod
        def from_service_account_info(info, scopes=None):
            return creds_obj if creds_obj is not None else MagicMock()

    sa_mod.Credentials = Credentials
    oauth2.service_account = sa_mod
    google.oauth2 = oauth2
    return {
        "google": google,
        "google.oauth2": oauth2,
        "google.oauth2.service_account": sa_mod,
    }


@pytest.fixture
def fake_google(monkeypatch):
    """Inyecta gspread + google-auth ficticios en sys.modules."""
    gspread = _fake_gspread_module()
    monkeypatch.setitem(sys.modules, "gspread", gspread)
    for name, mod in _fake_google_auth_modules().items():
        monkeypatch.setitem(sys.modules, name, mod)
    return gspread


# ── _authorize ────────────────────────────────────────────────────────────────


class TestAuthorize:
    def test_autorizacion_exitosa(self, fake_google):
        gc = MagicMock()
        fake_google.authorize.return_value = gc
        client = GoogleSheetsClient(SERVICE_ACCOUNT, drive_folder_id="folder1")
        assert client._gc is gc
        assert client._drive_folder_id == "folder1"

    def test_service_account_invalido_lanza_auth_error(self, fake_google):
        with pytest.raises(GoogleSheetsAuthError, match="client_email"):
            GoogleSheetsClient({"sin": "email"})

    def test_service_account_no_dict_lanza_auth_error(self, fake_google):
        with pytest.raises(GoogleSheetsAuthError):
            GoogleSheetsClient("no-soy-dict")

    def test_error_inesperado_en_authorize_se_envuelve_sin_filtrar_detalle(
        self, fake_google
    ):
        # gspread.authorize revienta → AuthError genérico, sin filtrar la clave.
        fake_google.authorize.side_effect = RuntimeError("clave secreta xyz")
        with pytest.raises(GoogleSheetsAuthError) as exc:
            GoogleSheetsClient(SERVICE_ACCOUNT)
        assert "clave secreta xyz" not in str(exc.value)
        assert "RuntimeError" in str(exc.value)

    def test_falta_dependencia_lanza_sheets_error(self, monkeypatch):
        # Simula que 'gspread' no está instalado.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "gspread":
                raise ImportError("no module named gspread")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(GoogleSheetsError, match="gspread"):
            GoogleSheetsClient(SERVICE_ACCOUNT)


# ── abrir_o_crear_spreadsheet ─────────────────────────────────────────────────


class TestAbrirOCrearSpreadsheet:
    def _client(self, fake_google, gc):
        fake_google.authorize.return_value = gc
        return GoogleSheetsClient(SERVICE_ACCOUNT)

    def test_abre_por_id_cuando_se_indica(self, fake_google):
        gc = MagicMock()
        sh = MagicMock()
        gc.open_by_key.return_value = sh
        client = self._client(fake_google, gc)
        assert client.abrir_o_crear_spreadsheet("T", "ID123") is sh
        gc.open_by_key.assert_called_once_with("ID123")

    def test_abrir_por_id_invalido_lanza_sheets_error(self, fake_google):
        gc = MagicMock()
        gc.open_by_key.side_effect = RuntimeError("403")
        client = self._client(fake_google, gc)
        with pytest.raises(GoogleSheetsError, match="No se pudo abrir"):
            client.abrir_o_crear_spreadsheet("T", "ID_MALO")

    def test_abre_por_titulo_si_no_hay_id(self, fake_google):
        gc = MagicMock()
        sh = MagicMock()
        gc.open.return_value = sh
        client = self._client(fake_google, gc)
        assert client.abrir_o_crear_spreadsheet("Mi Hoja") is sh
        gc.open.assert_called_once_with("Mi Hoja")

    def test_crea_si_no_existe_por_titulo(self, fake_google):
        gc = MagicMock()
        gc.open.side_effect = fake_google.SpreadsheetNotFound()
        nueva = MagicMock()
        gc.create.return_value = nueva
        client = GoogleSheetsClient(SERVICE_ACCOUNT, drive_folder_id="F1")
        client._gc = gc
        assert client.abrir_o_crear_spreadsheet("Nueva") is nueva
        gc.create.assert_called_once_with("Nueva", folder_id="F1")


# ── obtener_o_crear_worksheet ─────────────────────────────────────────────────


class TestObtenerOCrearWorksheet:
    def test_obtiene_existente(self, fake_google):
        fake_google.authorize.return_value = MagicMock()
        client = GoogleSheetsClient(SERVICE_ACCOUNT)
        sh = MagicMock()
        ws = MagicMock()
        sh.worksheet.return_value = ws
        assert client.obtener_o_crear_worksheet(sh, "Contactos", cols=5) is ws

    def test_crea_si_no_existe(self, fake_google):
        client = GoogleSheetsClient.__new__(GoogleSheetsClient)
        sh = MagicMock()
        sh.worksheet.side_effect = fake_google.WorksheetNotFound()
        nueva = MagicMock()
        sh.add_worksheet.return_value = nueva
        assert client.obtener_o_crear_worksheet(sh, "Productos", cols=3) is nueva
        sh.add_worksheet.assert_called_once_with(title="Productos", rows=100, cols=3)

    def test_crea_con_minimo_una_columna(self, fake_google):
        client = GoogleSheetsClient.__new__(GoogleSheetsClient)
        sh = MagicMock()
        sh.worksheet.side_effect = fake_google.WorksheetNotFound()
        client.obtener_o_crear_worksheet(sh, "X", cols=0)
        _, kwargs = sh.add_worksheet.call_args
        assert kwargs["cols"] == 1


# ── test (conectividad) ───────────────────────────────────────────────────────


class TestConectividad:
    def test_test_ok_cuenta_spreadsheets(self):
        client = GoogleSheetsClient.__new__(GoogleSheetsClient)
        client._gc = MagicMock()
        client._gc.list_spreadsheet_files.return_value = [1, 2, 3]
        assert client.test() == {"spreadsheets_visibles": 3}

    def test_test_falla_acceso_drive(self):
        client = GoogleSheetsClient.__new__(GoogleSheetsClient)
        client._gc = MagicMock()
        client._gc.list_spreadsheet_files.side_effect = RuntimeError("denied")
        with pytest.raises(GoogleSheetsError, match="Drive"):
            client.test()
