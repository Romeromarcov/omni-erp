"""
Tests del conector Google Sheets (export outbound).

Son tests unitarios: no tocan la API real de Google ni la BD. El cliente y la
planilla se mockean para verificar la lógica de proyección de columnas y de
upsert por fila.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.integration_hub.connectors.base import ConnectorNotSupportedError
from apps.integration_hub.connectors.google_sheets import columns
from apps.integration_hub.connectors.google_sheets.client import GoogleSheetsClient
from apps.integration_hub.connectors.google_sheets.connector import (
    GoogleSheetsConnector,
)

# ── columns.build_rows / _cell ────────────────────────────────────────────────


class TestColumnas:
    def test_entidades_soportadas_cubre_las_siete(self):
        assert set(columns.entidades_soportadas()) == {
            "contactos",
            "productos",
            "pedidos_venta",
            "pedidos_compra",
            "facturas_venta",
            "pagos",
            "inventario",
        }

    def test_indice_clave_es_id_externo_en_posicion_cero(self):
        for tipo in columns.entidades_soportadas():
            assert columns.indice_clave(tipo) == 0
            assert columns.COLUMNAS[tipo][0][0] == "id_externo"

    def test_cell_booleano_a_si_no(self):
        assert columns._cell(True) == "Sí"
        assert columns._cell(False) == "No"

    def test_cell_decimal_preserva_precision_como_texto(self):
        assert columns._cell(Decimal("1234.56")) == "1234.56"
        assert columns._cell(Decimal("0")) == "0"

    def test_cell_decimal_negativo_no_se_protege_como_formula(self):
        # Los montos negativos llegan como Decimal → deben quedar numéricos.
        assert columns._cell(Decimal("-5.00")) == "-5.00"

    def test_cell_texto_con_formula_se_neutraliza(self):
        # Inyección de fórmulas en Sheets (CWE-1236): texto que empieza con
        # = + - @ se antepone con "'" para que se trate como literal.
        assert columns._cell("=1+1") == "'=1+1"
        assert columns._cell("@SUM(A1)") == "'@SUM(A1)"
        assert columns._cell("-cmd") == "'-cmd"
        assert columns._cell("Texto normal") == "Texto normal"

    def test_cell_none_y_vacio_a_string_vacio(self):
        assert columns._cell(None) == ""
        assert columns._cell("") == ""

    def test_cell_lista_y_dict_a_json(self):
        assert columns._cell([{"x": 1}]) == '[{"x": 1}]'
        assert columns._cell({"a": "ñ"}) == '{"a": "ñ"}'

    def test_build_rows_contactos_proyecta_columnas_en_orden(self):
        registros = [
            {
                "id_externo": "7",
                "nombre": "ACME",
                "email": "a@acme.com",
                "es_cliente": True,
                "es_proveedor": False,
                "activo": True,
                "_checksum": "abc",
                "_fuente": "odoo",
            }
        ]
        header, rows = columns.build_rows("contactos", registros)
        assert header[0] == "ID Externo"
        assert rows[0][0] == "7"
        assert rows[0][1] == "ACME"
        # bool → Sí/No; el _checksum NO debe aparecer
        assert "Sí" in rows[0] and "No" in rows[0]
        assert "abc" not in rows[0]

    def test_build_rows_pedido_serializa_lineas_a_json(self):
        registros = [
            {
                "id_externo": "10",
                "numero": "S0001",
                "total": Decimal("99.90"),
                "lineas": [{"producto": "X", "cantidad": 2}],
            }
        ]
        header, rows = columns.build_rows("pedidos_venta", registros)
        idx = [c for c, _ in columns.COLUMNAS["pedidos_venta"]].index("lineas")
        assert rows[0][idx] == '[{"producto": "X", "cantidad": 2}]'


# ── GoogleSheetsClient.upsert / _fila_igual ──────────────────────────────────


class TestGoogleSheetsClientUpsert:
    def _client(self):
        # Saltar __init__ (no queremos autenticar contra Google en un test unit).
        return GoogleSheetsClient.__new__(GoogleSheetsClient)

    def test_upsert_hoja_vacia_escribe_todo(self):
        client = self._client()
        ws = MagicMock()
        ws.get_all_values.return_value = []
        creados, act, omit = client.upsert(
            ws, ["ID Externo", "Nombre"], [["1", "A"], ["2", "B"]], key_index=0
        )
        assert (creados, act, omit) == (2, 0, 0)
        ws.update.assert_called_once()
        ws.append_rows.assert_not_called()

    def test_upsert_actualiza_cambiadas_omite_iguales_agrega_nuevas(self):
        client = self._client()
        ws = MagicMock()
        # Encabezado + 2 filas existentes (id 1 igual, id 2 cambiará).
        ws.get_all_values.return_value = [
            ["ID Externo", "Nombre"],
            ["1", "A"],
            ["2", "B"],
        ]
        rows = [
            ["1", "A"],  # sin cambios → omitido
            ["2", "B2"],  # cambió → actualizado
            ["3", "C"],  # nuevo → creado
        ]
        creados, act, omit = client.upsert(
            ws, ["ID Externo", "Nombre"], rows, key_index=0
        )
        assert (creados, act, omit) == (1, 1, 1)
        ws.batch_update.assert_called_once()
        ws.append_rows.assert_called_once_with(
            [["3", "C"]], value_input_option="USER_ENTERED"
        )

    def test_fila_igual_rellena_celdas_truncadas(self):
        # Sheets recorta celdas vacías finales; deben considerarse iguales.
        assert GoogleSheetsClient._fila_igual(["1", "A"], ["1", "A", ""]) is True
        assert GoogleSheetsClient._fila_igual(["1", "A"], ["1", "B"]) is False

    def test_fila_igual_equivalencia_numerica(self):
        # USER_ENTERED coerciona "100.00"→100 y Sheets lo relee como "100":
        # los montos sin cambios NO deben reescribirse en cada corrida.
        assert GoogleSheetsClient._fila_igual(["1", "100"], ["1", "100.00"]) is True
        assert GoogleSheetsClient._fila_igual(["1", "99.9"], ["1", "99.90"]) is True
        assert GoogleSheetsClient._fila_igual(["1", "99.9"], ["1", "99.91"]) is False
        # No-numéricos siguen comparándose como texto exacto.
        assert GoogleSheetsClient._fila_igual(["1", "A1"], ["1", "A10"]) is False

    def test_upsert_monto_coercionado_se_omite_no_se_reescribe(self):
        client = self._client()
        ws = MagicMock()
        # Sheets devolvió el monto coercionado (100, no 100.00).
        ws.get_all_values.return_value = [
            ["ID Externo", "Monto"],
            ["1", "100"],
        ]
        creados, act, omit = client.upsert(
            ws, ["ID Externo", "Monto"], [["1", "100.00"]], key_index=0
        )
        assert (creados, act, omit) == (0, 0, 1)
        ws.batch_update.assert_not_called()

    def test_upsert_omite_filas_sin_clave(self):
        # id_externo vacío: sin clave no hay upsert → se omite (no duplica).
        client = self._client()
        ws = MagicMock()
        ws.get_all_values.return_value = [["ID Externo", "Nombre"], ["1", "A"]]
        creados, act, omit = client.upsert(
            ws, ["ID Externo", "Nombre"], [["", "Sin ID"], ["2", "B"]], key_index=0
        )
        assert (creados, act, omit) == (1, 0, 1)
        ws.append_rows.assert_called_once_with(
            [["2", "B"]], value_input_option="USER_ENTERED"
        )


# ── GoogleSheetsConnector.push_entidades / test_connection ───────────────────


class TestGoogleSheetsConnector:
    _SENTINEL = object()

    def _connector(self, config=_SENTINEL):
        if config is self._SENTINEL:
            config = {
                "service_account": {"client_email": "svc@proj.iam.gserviceaccount.com"}
            }
        instancia = MagicMock()
        instancia.get_config.return_value = config
        instancia.id_proveedor.codigo = "google_sheets"
        return GoogleSheetsConnector(instancia)

    def test_push_entidades_devuelve_contadores(self):
        conn = self._connector()
        fake_client = MagicMock()
        fake_client.obtener_o_crear_worksheet.return_value = MagicMock()
        fake_client.upsert.return_value = (2, 1, 0)
        conn._client = fake_client
        conn._spreadsheet = MagicMock()

        registros = [
            {"id_externo": "1", "nombre": "A"},
            {"id_externo": "2", "nombre": "B"},
            {"id_externo": "3", "nombre": "C"},
        ]
        res = conn.push_entidades("contactos", registros)
        assert res.total == 3
        assert res.creados == 2
        assert res.actualizados == 1
        assert res.exitoso is True

    def test_push_entidades_lote_vacio_no_llama_cliente(self):
        conn = self._connector()
        conn._client = MagicMock()
        conn._spreadsheet = MagicMock()
        res = conn.push_entidades("contactos", [])
        assert res.total == 0
        conn._client.upsert.assert_not_called()

    def test_push_entidades_entidad_no_soportada_lanza(self):
        conn = self._connector()
        with pytest.raises(ConnectorNotSupportedError):
            conn.push_entidades("entidad_inexistente", [{"id_externo": "1"}])

    def test_test_connection_exitosa(self):
        conn = self._connector()
        fake_client = MagicMock()
        fake_client.test.return_value = {"spreadsheets_visibles": 3}
        conn._client = fake_client
        res = conn.test_connection()
        assert res.success is True
        assert res.details == {"spreadsheets_visibles": 3}

    def test_test_connection_falla_sin_service_account(self):
        conn = self._connector(config={})
        res = conn.test_connection()
        assert res.success is False
        assert "service_account" in res.message
