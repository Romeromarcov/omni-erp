"""
GoogleSheetsConnector — conector de DESTINO del Integration Hub.

Exporta entidades canónicas (las que entrega un conector de origen como Odoo) a
hojas de Google Sheets, **una pestaña por entidad**. Es un conector *outbound*:
implementa ``push_entidades()``; no soporta ``pull_*``.

Configuración esperada en ``ConectorInstancia.configuracion`` (cifrada en reposo,
H-SEC-4 — nunca loguear, R-CODE-8)::

    {
        "service_account": { ... JSON de la cuenta de servicio ... },  # requerido
        "spreadsheet_id": "abc...",            # opcional: usar una planilla existente
        "drive_folder_id": "xyz...",           # opcional: carpeta donde crearla
        "titulo": "Omni Export - Lubrikca",    # opcional: título si se auto-crea
        "source_instancia_id": "uuid"          # instancia origen (la usa ExportEngine)
    }
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    ConnectorDataError,
    ConnectorNotSupportedError,
    SyncResult,
    TestConnectionResult,
)
from apps.integration_hub.connectors.google_sheets import columns
from apps.integration_hub.connectors.google_sheets.client import (
    GoogleSheetsAuthError,
    GoogleSheetsClient,
    GoogleSheetsError,
)

if TYPE_CHECKING:
    from apps.integration_hub.models import ConectorInstancia

logger = logging.getLogger(__name__)

TITULO_DEFECTO = "Omni Export"


class GoogleSheetsConnector(BaseConnector):
    """Conector outbound que exporta entidades canónicas a Google Sheets."""

    PROVIDER_CODE = "google_sheets"
    PROVIDER_NAME = "Google Sheets"
    SUPPORTED_ENTITIES = columns.entidades_soportadas()

    def __init__(self, instancia: "ConectorInstancia"):
        super().__init__(instancia)
        self._client: GoogleSheetsClient | None = None
        self._spreadsheet = None
        # ID de la planilla efectivamente usada (el ExportEngine lo persiste si
        # se auto-creó, para reutilizarla en próximas exportaciones).
        self.spreadsheet_id = self._config.get("spreadsheet_id", "")

    def _get_client(self) -> GoogleSheetsClient:
        if self._client is not None:
            return self._client
        sa = self._config.get("service_account")
        if not sa:
            raise ConnectorConnectionError(
                "Falta 'service_account' en la configuración del conector Google Sheets."
            )
        try:
            self._client = GoogleSheetsClient(
                sa, drive_folder_id=self._config.get("drive_folder_id", "")
            )
        except GoogleSheetsAuthError as exc:
            raise ConnectorConnectionError(str(exc)) from exc
        return self._client

    def _get_spreadsheet(self):
        if self._spreadsheet is not None:
            return self._spreadsheet
        client = self._get_client()
        titulo = self._config.get("titulo") or TITULO_DEFECTO
        try:
            sh = client.abrir_o_crear_spreadsheet(titulo, self.spreadsheet_id)
        except GoogleSheetsError as exc:
            raise ConnectorDataError(str(exc)) from exc
        self._spreadsheet = sh
        self.spreadsheet_id = getattr(sh, "id", self.spreadsheet_id)
        return sh

    # ── Conexión ───────────────────────────────────────────────────────────

    def test_connection(self) -> TestConnectionResult:
        try:
            info = self._get_client().test()
            return TestConnectionResult(
                success=True,
                message="Conexión con Google Sheets exitosa.",
                version="google-sheets-v4",
                details=info,
            )
        except (ConnectorConnectionError, GoogleSheetsError) as exc:
            return TestConnectionResult(success=False, message=str(exc))
        except Exception as exc:
            return TestConnectionResult(
                success=False, message=f"Error inesperado: {type(exc).__name__}"
            )

    def get_version_info(self) -> dict:
        return {"api": "google-sheets-v4", "auth": "service_account"}

    # ── Export (outbound) ────────────────────────────────────────────────────

    def push_entidades(self, tipo_entidad: str, registros: list[dict]) -> SyncResult:
        """Exporta un lote de registros canónicos a la pestaña de su entidad."""
        if tipo_entidad not in self.SUPPORTED_ENTITIES:
            raise ConnectorNotSupportedError(
                f"Google Sheets no soporta exportar la entidad '{tipo_entidad}'."
            )

        resultado = SyncResult(tipo_entidad=tipo_entidad, total=len(registros))
        if not registros:
            return resultado

        header, rows = columns.build_rows(tipo_entidad, registros)
        key_index = columns.indice_clave(tipo_entidad)
        sh = self._get_spreadsheet()
        ws = self._get_client().obtener_o_crear_worksheet(
            sh, columns.hoja_de(tipo_entidad), cols=len(header)
        )
        try:
            creados, actualizados, omitidos = self._get_client().upsert(
                ws, header, rows, key_index=key_index
            )
        except GoogleSheetsError as exc:
            raise ConnectorDataError(str(exc)) from exc

        resultado.creados = creados
        resultado.actualizados = actualizados
        resultado.omitidos = omitidos
        return resultado
