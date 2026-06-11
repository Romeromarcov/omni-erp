"""
GoogleSheetsClient — cliente de escritura a Google Sheets para el Hub.

Autenticación con **Service Account** (server-to-server, sin login interactivo).
La planilla y las pestañas se crean automáticamente si no existen. La escritura
es por **upsert**: las filas existentes (clave ``id_externo``) se actualizan y
las nuevas se agregan, sin borrar el resto del contenido de la hoja.

``gspread`` y ``google-auth`` se importan de forma perezosa para que el módulo
cargue aunque las dependencias no estén instaladas (p. ej. en ``manage.py
check`` o en entornos sin las libs de Google).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Sheets (lectura/escritura) + Drive restringido a archivos creados por la app.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleSheetsError(Exception):
    """Error genérico del cliente de Google Sheets."""


class GoogleSheetsAuthError(GoogleSheetsError):
    """Credenciales inválidas o fallo de autenticación."""


class GoogleSheetsClient:
    """Envuelve gspread para abrir/crear planillas y hacer upsert por fila."""

    def __init__(self, service_account_info: dict, drive_folder_id: str = ""):
        self._drive_folder_id = drive_folder_id or ""
        self._gc = self._authorize(service_account_info)

    @staticmethod
    def _authorize(service_account_info: dict):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise GoogleSheetsError(
                "Faltan dependencias 'gspread' y 'google-auth'. "
                "Instálalas con: pip install gspread google-auth."
            ) from exc

        if (
            not isinstance(service_account_info, dict)
            or "client_email" not in service_account_info
        ):
            raise GoogleSheetsAuthError(
                "El service account JSON es inválido o está incompleto "
                "(falta 'client_email')."
            )
        try:
            creds = Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
            return gspread.authorize(creds)
        except GoogleSheetsError:
            raise
        except Exception as exc:
            # No incluir el detalle del error (puede filtrar partes de la clave).
            raise GoogleSheetsAuthError(
                f"No se pudo autenticar con Google: {type(exc).__name__}"
            ) from exc

    # ── Spreadsheet / Worksheet ────────────────────────────────────────────

    def abrir_o_crear_spreadsheet(self, titulo: str, spreadsheet_id: str = ""):
        """Abre una planilla por ID; sin ID, la busca por título o la crea."""
        import gspread

        if spreadsheet_id:
            try:
                return self._gc.open_by_key(spreadsheet_id)
            except Exception as exc:
                raise GoogleSheetsError(
                    f"No se pudo abrir la planilla indicada ({type(exc).__name__}). "
                    "Verifica el ID y que la cuenta de servicio tenga acceso "
                    "(compártela con el email del service account)."
                ) from exc
        try:
            return self._gc.open(titulo)
        except gspread.SpreadsheetNotFound:
            return self._gc.create(titulo, folder_id=self._drive_folder_id or None)

    def obtener_o_crear_worksheet(self, spreadsheet, titulo: str, cols: int):
        """Obtiene la pestaña por título o la crea con el ancho indicado."""
        import gspread

        try:
            return spreadsheet.worksheet(titulo)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=titulo, rows=100, cols=max(cols, 1))

    # ── Upsert por fila ────────────────────────────────────────────────────

    def upsert(self, worksheet, header: list, rows: list, key_index: int = 0):
        """
        Inserta/actualiza filas usando la columna ``key_index`` como clave.

        - Hoja vacía → escribe encabezado + todas las filas (todas "creadas").
        - Hoja con datos → actualiza las filas cuya clave ya existe (solo si
          cambiaron) y agrega las nuevas al final.

        Devuelve ``(creados, actualizados, omitidos)``.

        Las filas sin clave (``id_externo`` vacío) se omiten: sin clave no hay
        upsert posible y se acumularían duplicados en cada corrida.
        """
        sin_clave = sum(1 for fila in rows if str(fila[key_index]) == "")
        if sin_clave:
            logger.warning(
                "upsert: %s fila(s) sin clave en col %s — omitidas.",
                sin_clave,
                key_index,
            )
            rows = [fila for fila in rows if str(fila[key_index]) != ""]

        existentes = worksheet.get_all_values()
        if not existentes:
            worksheet.update(
                range_name="A1",
                values=[header] + rows,
                value_input_option="USER_ENTERED",
            )
            return len(rows), 0, sin_clave

        header_actual = existentes[0]
        data = existentes[1:]
        indice: dict[str, int] = {}
        for offset, fila in enumerate(data):
            if len(fila) > key_index and fila[key_index] != "":
                # +2: 1 por el encabezado, 1 porque las filas de Sheets son 1-based.
                indice[fila[key_index]] = offset + 2

        actualizaciones: list[tuple[str, list]] = []
        nuevas: list[list] = []
        creados = actualizados = 0
        omitidos = sin_clave

        if header_actual != header:
            actualizaciones.append(("A1", [header]))

        for fila in rows:
            clave = str(fila[key_index])
            if clave in indice:
                rownum = indice[clave]
                if self._fila_igual(data[rownum - 2], fila):
                    omitidos += 1
                    continue
                actualizaciones.append((f"A{rownum}", [fila]))
                actualizados += 1
            else:
                nuevas.append(fila)
                creados += 1

        if actualizaciones:
            worksheet.batch_update(
                [{"range": rng, "values": vals} for rng, vals in actualizaciones],
                value_input_option="USER_ENTERED",
            )
        if nuevas:
            worksheet.append_rows(nuevas, value_input_option="USER_ENTERED")

        return creados, actualizados, omitidos

    @classmethod
    def _fila_igual(cls, actual: list, nueva: list) -> bool:
        """
        Compara filas celda a celda (Sheets devuelve siempre strings).

        Las celdas extra al final de ``actual`` se ignoran a propósito: son
        columnas/anotaciones manuales del usuario que el upsert debe preservar.
        """
        nueva_str = [str(v) if v != "" else "" for v in nueva]
        if len(actual) < len(nueva_str):
            # Sheets recorta las celdas vacías finales: rellenar para comparar.
            actual = actual + [""] * (len(nueva_str) - len(actual))
        return all(
            cls._celda_igual(a, n) for a, n in zip(actual[: len(nueva_str)], nueva_str)
        )

    @staticmethod
    def _celda_igual(actual: str, nueva: str) -> bool:
        """
        Compara una celda leída de Sheets con el valor a escribir.

        USER_ENTERED coerciona los strings numéricos: "100.00" se almacena como
        100 y se relee como "100". Comparar solo como texto reescribiría TODAS
        las filas monetarias en cada corrida; si ambas celdas parsean como
        número, se comparan por equivalencia Decimal ("99.90" == "99.9").
        """
        if actual == nueva:
            return True
        from decimal import Decimal, InvalidOperation

        try:
            return Decimal(actual) == Decimal(nueva)
        except (InvalidOperation, ValueError, TypeError):
            return False

    # ── Conectividad ───────────────────────────────────────────────────────

    def test(self) -> dict:
        """Valida credenciales con una llamada liviana a Drive."""
        try:
            archivos = self._gc.list_spreadsheet_files()
        except Exception as exc:
            raise GoogleSheetsError(
                f"Autenticación OK pero falló el acceso a Drive: {type(exc).__name__}"
            ) from exc
        return {"spreadsheets_visibles": len(archivos)}
