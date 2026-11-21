"""
Tests del OdooXMLRPCClient (connectors/odoo/client.py) y de las ramas
restantes del OdooConnector (connectors/odoo/connector.py).

TODO xmlrpc está mockeado con unittest.mock.patch — CERO red real.
Complementa apps/integration_hub/tests/test_odoo_connector.py (no duplica).
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from xmlrpc.client import Fault

from apps.integration_hub.connectors.base import (
    ConnectorConnectionError,
    ConnectorDataError,
)
from apps.integration_hub.connectors.odoo.client import (
    OdooAuthError,
    OdooCallError,
    OdooXMLRPCClient,
)
from apps.integration_hub.connectors.odoo.connector import OdooConnector

pytestmark = pytest.mark.integration


def _make_client(**kwargs):
    """Cliente con autenticación mockeada (patrón de tests in-app)."""
    with patch("xmlrpc.client.ServerProxy") as mock_proxy:
        mock_common = MagicMock()
        mock_common.authenticate.return_value = 7
        mock_common.version.return_value = {"server_version": "17.0", "protocol_version": 1}
        mock_models = MagicMock()
        mock_proxy.side_effect = [mock_common, mock_models]

        client = OdooXMLRPCClient(
            host=kwargs.pop("host", "test.odoo.com"),
            db=kwargs.pop("db", "testdb"),
            user=kwargs.pop("user", "admin@test.com"),
            api_key=kwargs.pop("api_key", "key123"),
            **kwargs,
        )
        client._models = mock_models
        return client, mock_models


def _domain_de(mock_models):
    """Extrae el argumento posicional 'domain' del último execute_kw."""
    return mock_models.execute_kw.call_args[0][5]


def _kwargs_de(mock_models):
    return mock_models.execute_kw.call_args[0][6]


# ── Cliente: construcción y autenticación ────────────────────────────────────


class TestClienteConstruccion:
    def test_host_sin_esquema_recibe_https(self):
        client, _ = _make_client(host="miodoo.odoo.com/")
        assert client._host == "https://miodoo.odoo.com"
        assert client._common_url == "https://miodoo.odoo.com/xmlrpc/2/common"
        assert client._object_url == "https://miodoo.odoo.com/xmlrpc/2/object"

    def test_host_con_esquema_http_se_respeta(self):
        client, _ = _make_client(host="http://localhost:8069")
        assert client._host == "http://localhost:8069"

    def test_version_fallida_no_impide_autenticar(self):
        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_common = MagicMock()
            mock_common.version.side_effect = RuntimeError("no version endpoint")
            mock_common.authenticate.return_value = 3
            mock_models = MagicMock()
            mock_proxy.side_effect = [mock_common, mock_models]

            client = OdooXMLRPCClient("x.odoo.com", "db", "u", "k")
            assert client.uid == 3
            assert client.get_version() == {}

    def test_error_de_conexion_lanza_autherror_sin_api_key(self):
        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_proxy.side_effect = ConnectionError("api_key=ultrasecreta refused")
            with pytest.raises(OdooAuthError) as exc_info:
                OdooXMLRPCClient("x.odoo.com", "db", "u", "ultrasecreta")
        # R-CODE-8: el mensaje solo expone el tipo, nunca el detalle con secretos
        assert "ConnectionError" in str(exc_info.value)
        assert "ultrasecreta" not in str(exc_info.value)

    def test_get_version_retorna_info_detectada(self):
        client, _ = _make_client()
        assert client.get_version() == {"server_version": "17.0", "protocol_version": 1}


class TestClienteCall:
    def test_call_con_fault_lanza_odoocallerror(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.side_effect = Fault(3, "Access Denied")
        with pytest.raises(OdooCallError) as exc_info:
            client.call("res.partner", "search_read")
        assert "Access Denied" in str(exc_info.value)
        assert "res.partner.search_read" in str(exc_info.value)

    def test_call_con_error_generico_lanza_odoocallerror(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.side_effect = TimeoutError("lento")
        with pytest.raises(OdooCallError) as exc_info:
            client.call("sale.order", "read")
        assert "TimeoutError" in str(exc_info.value)

    def test_call_sin_domain_usa_lista_vacia(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = 0
        client.call("res.lang", "search_count")
        assert _domain_de(mock_models) == [[]]
        assert _kwargs_de(mock_models) == {}


# ── Cliente: métodos de lectura (domains exactos) ─────────────────────────────


class TestClienteLectura:
    def test_get_socios_filtros_combinados(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_socios(cliente=True, proveedor=True, desde="2024-01-01", limite=99)
        assert _domain_de(mock_models) == [
            [
                ["active", "=", True],
                ["customer_rank", ">", 0],
                ["supplier_rank", ">", 0],
                ["write_date", ">=", "2024-01-01"],
            ]
        ]
        assert _kwargs_de(mock_models)["limit"] == 99

    def test_get_socios_sin_filtros(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_socios()
        assert _domain_de(mock_models) == [[["active", "=", True]]]
        assert _kwargs_de(mock_models)["limit"] == 500

    def test_buscar_socio_por_nombre(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = [{"id": 1, "name": "ACME"}]
        result = client.buscar_socio("ACM", limite=5)
        assert result == [{"id": 1, "name": "ACME"}]
        assert _domain_de(mock_models) == [
            [
                ["name", "ilike", "ACM"],
                ["active", "=", True],
            ]
        ]
        assert _kwargs_de(mock_models)["limit"] == 5

    def test_get_productos_con_desde(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_productos(desde="2024-02-01")
        assert _domain_de(mock_models) == [
            [
                ["active", "=", True],
                ["write_date", ">=", "2024-02-01"],
            ]
        ]

    def test_get_variantes_producto(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_variantes_producto(42)
        assert _domain_de(mock_models) == [
            [
                ["product_tmpl_id", "=", 42],
                ["active", "=", True],
            ]
        ]

    def test_get_pedidos_venta_solo_confirmadas(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_pedidos_venta(solo_confirmadas=True)
        assert _domain_de(mock_models) == [[["state", "in", ["sale", "done"]]]]

    def test_get_pedidos_venta_incluye_borradores(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_pedidos_venta(solo_confirmadas=False, desde="2024-03-01")
        assert _domain_de(mock_models) == [
            [
                ["state", "in", ["draft", "sent", "sale", "done"]],
                ["write_date", ">=", "2024-03-01"],
            ]
        ]

    def test_get_lineas_pedido_venta(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_lineas_pedido_venta(10)
        assert _domain_de(mock_models) == [[["order_id", "=", 10]]]

    def test_get_pedidos_compra(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_pedidos_compra(desde="2024-01-01")
        assert _domain_de(mock_models) == [
            [
                ["state", "in", ["purchase", "done"]],
                ["write_date", ">=", "2024-01-01"],
            ]
        ]

    def test_get_lineas_pedido_compra(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_lineas_pedido_compra(8)
        assert _domain_de(mock_models) == [[["order_id", "=", 8]]]

    def test_get_facturas_tipo_y_desde(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_facturas(tipo="in_invoice", desde="2024-05-01")
        assert _domain_de(mock_models) == [
            [
                ["move_type", "=", "in_invoice"],
                ["state", "=", "posted"],
                ["write_date", ">=", "2024-05-01"],
            ]
        ]

    def test_get_pagos_con_tipo(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_pagos(tipo="inbound", desde="2024-04-01")
        assert _domain_de(mock_models) == [
            [
                ["state", "in", ["in_process", "paid", "posted"]],
                ["payment_type", "=", "inbound"],
                ["date", ">=", "2024-04-01"],
            ]
        ]

    def test_get_stock_actual_solo_ubicaciones_internas(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_stock_actual(limite=50)
        assert _domain_de(mock_models) == [[["location_id.usage", "=", "internal"]]]
        assert _kwargs_de(mock_models)["limit"] == 50

    def test_get_movimientos_stock(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_movimientos_stock(desde="2024-06-01")
        assert _domain_de(mock_models) == [
            [
                ["state", "=", "done"],
                ["date", ">=", "2024-06-01"],
            ]
        ]

    def test_get_diarios_con_tipos(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_diarios(tipos=["bank", "cash"])
        assert _domain_de(mock_models) == [[["type", "in", ["bank", "cash"]]]]

    def test_get_diarios_sin_tipos(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_diarios()
        assert _domain_de(mock_models) == [[]]

    def test_get_monedas_y_paises(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = []
        client.get_monedas()
        assert _domain_de(mock_models) == [[["active", "=", True]]]
        client.get_paises()
        assert _domain_de(mock_models) == [[]]


# ── Cliente: escritura ────────────────────────────────────────────────────────


class TestClienteEscritura:
    def test_crear_socio_limpia_nones_y_retorna_id(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = 88
        nuevo_id = client.crear_socio({"name": "ACME", "email": None})
        assert nuevo_id == 88
        assert _domain_de(mock_models) == [{"name": "ACME"}]

    def test_crear_socio_resultado_lista_toma_primero(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = [99]
        assert client.crear_socio({"name": "X"}) == 99

    def test_actualizar_socio(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = True
        ok = client.actualizar_socio(5, {"phone": "0212", "vat": None})
        assert ok is True
        assert _domain_de(mock_models) == [[5], {"phone": "0212"}]

    def test_crear_producto(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = 12
        assert client.crear_producto({"name": "Silla", "barcode": None}) == 12
        assert _domain_de(mock_models) == [{"name": "Silla"}]

    def test_actualizar_producto(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.return_value = True
        assert client.actualizar_producto(3, {"list_price": 10.0}) is True
        assert _domain_de(mock_models) == [[3], {"list_price": 10.0}]


# ── Conector: _get_client y pulls ─────────────────────────────────────────────


def _connector(config=None):
    instancia = MagicMock()
    instancia.get_config.return_value = config or {
        "host": "https://test.odoo.com",
        "db": "testdb",
        "user": "admin@test.com",
        "api_key": "key123",
    }
    instancia.id_proveedor.codigo = "odoo"
    return OdooConnector(instancia)


def _connector_con_cliente_mock():
    connector = _connector()
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    connector._client = mock_client
    return connector, mock_client


class TestConnectorGetClient:
    def test_config_incompleta_lanza_connectionerror(self):
        connector = _connector(config={"host": "x", "user": "u"})  # sin api_key
        with pytest.raises(ConnectorConnectionError) as exc_info:
            connector._get_client()
        assert "incompleta" in str(exc_info.value)

    def test_autherror_se_convierte_en_connectionerror(self):
        connector = _connector()
        with patch(
            "apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient",
            side_effect=OdooAuthError("Autenticación Odoo fallida"),
        ):
            with pytest.raises(ConnectorConnectionError) as exc_info:
                connector._get_client()
        assert "Autenticación Odoo fallida" in str(exc_info.value)

    def test_cliente_existente_con_ping_ok_se_reusa(self):
        connector, mock_client = _connector_con_cliente_mock()
        assert connector._get_client() is mock_client

    def test_ping_fallido_reconecta(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.ping.return_value = False
        nuevo = MagicMock()
        with patch(
            "apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient",
            return_value=nuevo,
        ):
            assert connector._get_client() is nuevo

    def test_ping_con_excepcion_reconecta(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.ping.side_effect = RuntimeError("socket roto")
        nuevo = MagicMock()
        with patch(
            "apps.integration_hub.connectors.odoo.connector.OdooXMLRPCClient",
            return_value=nuevo,
        ):
            assert connector._get_client() is nuevo

    def test_get_version_info_delega_al_cliente(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_version.return_value = {"server_version": "16.0"}
        assert connector.get_version_info() == {"server_version": "16.0"}

    def test_test_connection_error_inesperado(self):
        connector = _connector()
        with patch.object(connector, "_get_client", side_effect=ValueError("raro")):
            result = connector.test_connection()
        assert result.success is False
        assert result.message == "Error inesperado: ValueError"
        assert result.details == {"error": "raro"}


class TestConnectorPullErrores:
    @pytest.mark.parametrize(
        "metodo,cliente_attr",
        [
            ("pull_contactos", "get_socios"),
            ("pull_productos", "get_productos"),
            ("pull_pedidos_venta", "get_pedidos_venta"),
            ("pull_pedidos_compra", "get_pedidos_compra"),
            ("pull_facturas_venta", "get_facturas"),
            ("pull_facturas_compra", "get_facturas"),
            ("pull_pagos", "get_pagos"),
            ("pull_inventario", "get_stock_actual"),
        ],
    )
    def test_odoocallerror_se_convierte_en_dataerror(self, metodo, cliente_attr):
        connector, mock_client = _connector_con_cliente_mock()
        getattr(mock_client, cliente_attr).side_effect = OdooCallError("falla rpc")
        with pytest.raises(ConnectorDataError) as exc_info:
            getattr(connector, metodo)()
        assert "falla rpc" in str(exc_info.value)

    def test_pull_contactos_pasa_desde_formateado(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_socios.return_value = []
        connector.pull_contactos(desde=datetime(2024, 3, 1, 12, 30, 45), limite=10)
        mock_client.get_socios.assert_called_once_with(desde="2024-03-01 12:30:45", limite=10)

    def test_pull_pagos_usa_solo_fecha(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_pagos.return_value = []
        connector.pull_pagos(desde=datetime(2024, 3, 1, 12, 30, 45))
        mock_client.get_pagos.assert_called_once_with(desde="2024-03-01", limite=300)


class TestConnectorPedidosYNormalizacion:
    def test_pull_pedidos_venta_incluye_lineas(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_pedidos_venta.return_value = [
            {
                "id": 5,
                "name": "SO005",
                "partner_id": [3, "Cliente Uno"],
                "user_id": [2, "Vendedor"],
                "date_order": "2024-03-01 10:00:00",
                "state": "sale",
                "invoice_status": "to invoice",
                "amount_untaxed": 100.0,
                "amount_tax": 16.0,
                "amount_total": 116.0,
                "currency_id": [2, "USD"],
                "pricelist_id": [1, "Lista Pública"],
                "payment_term_id": [4, "30 días"],
                "write_date": "2024-03-01 11:00:00",
            }
        ]
        mock_client.get_lineas_pedido_venta.return_value = [{"id": 50}]

        result = connector.pull_pedidos_venta()

        assert len(result) == 1
        pedido = result[0]
        assert pedido["id_externo"] == "5"
        assert pedido["numero"] == "SO005"
        assert pedido["cliente_id_externo"] == "3"
        assert pedido["cliente_nombre"] == "Cliente Uno"
        assert pedido["estado"] == "confirmado"
        assert pedido["estado_factura"] == "por_facturar"
        assert pedido["fecha_pedido"] == "2024-03-01"
        assert pedido["subtotal"] == Decimal("100.0")
        assert pedido["impuestos"] == Decimal("16.0")
        assert pedido["total"] == Decimal("116.0")
        assert pedido["moneda"] == "USD"
        assert pedido["termino_pago"] == "30 días"
        assert pedido["lineas"] == [{"id": 50}]

    def test_pull_pedidos_venta_error_en_lineas_deja_lista_vacia(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_pedidos_venta.return_value = [{"id": 5, "name": "SO005"}]
        mock_client.get_lineas_pedido_venta.side_effect = OdooCallError("sin acceso")
        result = connector.pull_pedidos_venta()
        assert result[0]["lineas"] == []

    def test_pull_pedidos_compra_normaliza(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_pedidos_compra.return_value = [
            {
                "id": 9,
                "name": "PO009",
                "partner_id": [7, "Proveedor XYZ"],
                "date_order": "2024-02-10 08:00:00",
                "date_approve": "2024-02-11 09:00:00",
                "state": "purchase",
                "invoice_status": "invoiced",
                "amount_untaxed": 200.0,
                "amount_tax": 32.0,
                "amount_total": 232.0,
                "currency_id": [2, "USD"],
            }
        ]
        mock_client.get_lineas_pedido_compra.return_value = []

        result = connector.pull_pedidos_compra()
        compra = result[0]
        assert compra["id_externo"] == "9"
        assert compra["proveedor_id_externo"] == "7"
        assert compra["proveedor_nombre"] == "Proveedor XYZ"
        assert compra["fecha_aprobacion"] == "2024-02-11"
        assert compra["total"] == Decimal("232.0")

    def test_pull_facturas_venta_normaliza(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_facturas.return_value = [
            {
                "id": 30,
                "name": "INV/2024/0001",
                "ref": "REF-1",
                "invoice_origin": "SO005",
                "partner_id": [3, "Cliente Uno"],
                "invoice_date": "2024-03-05",
                "invoice_date_due": "2024-04-04",
                "amount_untaxed": 100.0,
                "amount_tax": 16.0,
                "amount_total": 116.0,
                "amount_residual": 50.0,
                "currency_id": [2, "USD"],
                "payment_state": "partial",
            }
        ]
        result = connector.pull_facturas_venta()
        factura = result[0]
        assert factura["numero"] == "INV/2024/0001"
        assert factura["origen_pedido"] == "SO005"
        assert factura["fecha_vencimiento"] == "2024-04-04"
        assert factura["saldo_pendiente"] == Decimal("50.0")
        assert factura["estado_pago"] == "parcial"
        mock_client.get_facturas.assert_called_once_with(tipo="out_invoice", desde=None, limite=200)

    def test_pull_facturas_compra_normaliza(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_facturas.return_value = [
            {
                "id": 31,
                "name": "BILL/2024/0001",
                "ref": "PROV-FAC-9",
                "invoice_origin": "PO009",
                "partner_id": [7, "Proveedor XYZ"],
                "invoice_date": "2024-03-10",
                "invoice_date_due": "2024-04-09",
                "amount_untaxed": 200.0,
                "amount_tax": 32.0,
                "amount_total": 232.0,
                "amount_residual": 100.0,
                "currency_id": [2, "USD"],
                "payment_state": "partial",
            }
        ]
        mock_client.get_lineas_factura.return_value = [{"id": 91, "product_id": [10, "Prod"], "quantity": 2}]
        result = connector.pull_facturas_compra()
        factura = result[0]
        assert factura["id_externo"] == "31"
        assert factura["numero"] == "BILL/2024/0001"
        assert factura["referencia"] == "PROV-FAC-9"
        assert factura["origen_pedido"] == "PO009"
        assert factura["proveedor_id_externo"] == "7"
        assert factura["proveedor_nombre"] == "Proveedor XYZ"
        assert factura["total"] == Decimal("232.0")
        assert factura["saldo_pendiente"] == Decimal("100.0")
        assert factura["estado_pago"] == "parcial"
        assert len(factura["lineas"]) == 1
        mock_client.get_facturas.assert_called_once_with(tipo="in_invoice", desde=None, limite=200)

    def test_pull_inventario_normaliza_quants(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.get_stock_actual.return_value = [
            {
                "id": 70,
                "product_id": [10, "Silla"],
                "location_id": [4, "WH/Stock"],
                "quantity": 20.0,
                "reserved_quantity": 5.0,
                "lot_id": [2, "LOTE-A"],
            }
        ]
        result = connector.pull_inventario()
        quant = result[0]
        assert quant["id_externo"] == "70"
        assert quant["producto_id_externo"] == "10"
        assert quant["producto_nombre"] == "Silla"
        assert quant["ubicacion_nombre"] == "WH/Stock"
        assert quant["cantidad"] == 20.0
        assert quant["cantidad_reservada"] == 5.0
        assert quant["cantidad_disponible"] == 15.0
        assert quant["lote"] == "LOTE-A"

    def test_cantidad_disponible_nunca_negativa(self):
        connector, _ = _connector_con_cliente_mock()
        quant = connector._normalizar_stock_quant({"id": 1, "quantity": 2.0, "reserved_quantity": 5.0})
        assert quant["cantidad_disponible"] == 0.0


class TestConnectorPush:
    def test_push_contacto_nuevo_crea(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.crear_socio.return_value = 101
        result = connector.push_contacto(
            {
                "nombre": "ACME",
                "email": "a@b.com",
                "ciudad": "Caracas",
            }
        )
        assert result == "101"
        mock_client.crear_socio.assert_called_once_with(
            {
                "name": "ACME",
                "email": "a@b.com",
                "city": "Caracas",
            }
        )

    def test_push_contacto_existente_actualiza(self):
        connector, mock_client = _connector_con_cliente_mock()
        result = connector.push_contacto(
            {
                "id_externo": "42",
                "telefono": "0212",
                "identificador_fiscal": "J-1",
            }
        )
        assert result == "42"
        mock_client.actualizar_socio.assert_called_once_with(42, {"phone": "0212", "vat": "J-1"})

    def test_push_producto_nuevo_convierte_decimal_a_float(self):
        connector, mock_client = _connector_con_cliente_mock()
        mock_client.crear_producto.return_value = 55
        result = connector.push_producto(
            {
                "nombre": "Silla",
                "codigo_interno": "S-1",
                "precio_venta": Decimal("12.50"),
                "costo": Decimal("8.25"),
            }
        )
        assert result == "55"
        vals = mock_client.crear_producto.call_args[0][0]
        assert vals["list_price"] == 12.5
        assert isinstance(vals["list_price"], float)
        assert vals["standard_price"] == 8.25

    def test_push_producto_existente_actualiza(self):
        connector, mock_client = _connector_con_cliente_mock()
        result = connector.push_producto(
            {
                "id_externo": "7",
                "descripcion_venta": "Desc",
            }
        )
        assert result == "7"
        mock_client.actualizar_producto.assert_called_once_with(7, {"description_sale": "Desc"})


class TestConnectorCartera:
    def test_odoo_base_url_exige_https_en_produccion(self, settings):
        settings.DEBUG = False
        connector = _connector(config={"host": "http://inseguro.local"})
        with pytest.raises(ConnectorConnectionError) as exc_info:
            connector._odoo_base_url(connector._config)
        assert "https://" in str(exc_info.value)

    def test_odoo_base_url_acepta_http_en_debug(self, settings):
        settings.DEBUG = True
        connector = _connector(config={"host": "http://localhost:8069/"})
        assert connector._odoo_base_url(connector._config) == "http://localhost:8069"

    def test_odoo_base_url_prefiere_clave_url(self, settings):
        settings.DEBUG = False
        connector = _connector(config={"url": "https://odoo.prod", "host": "http://x"})
        assert connector._odoo_base_url(connector._config) == "https://odoo.prod"

    def test_pull_cartera_vencida_clasifica_buckets(self, settings):
        settings.DEBUG = True
        connector = _connector(
            config={
                "host": "http://localhost:8069",
                "db": "db",
                "uid": 2,
                "password": "p",
            }
        )
        hoy = date.today()
        records = [
            {  # vencida 45 días → bucket 31_60
                "id": 1,
                "partner_id": [3, "ACME"],
                "name": "INV-1",
                "amount_total": 100.0,
                "amount_residual": 40.0,
                "invoice_date_due": (hoy - timedelta(days=45)).isoformat(),
                "invoice_payment_state": "not_paid",
            },
            {  # al día → filtrada con solo_vencidas=True
                "id": 2,
                "partner_id": [4, "Beta"],
                "name": "INV-2",
                "amount_total": 50.0,
                "amount_residual": 50.0,
                "invoice_date_due": (hoy + timedelta(days=10)).isoformat(),
            },
            {  # fecha inválida → sin_fecha, filtrada con solo_vencidas
                "id": 3,
                "partner_id": [5, "Gamma"],
                "name": "INV-3",
                "amount_total": 10.0,
                "amount_residual": 10.0,
                "invoice_date_due": "fecha-rota",
            },
        ]
        mock_proxy_instance = MagicMock()
        mock_proxy_instance.execute_kw.return_value = records

        with patch("xmlrpc.client.ServerProxy", return_value=mock_proxy_instance):
            resultado = connector.pull_cartera_vencida(solo_vencidas=True)

        assert len(resultado) == 1
        partida = resultado[0]
        assert partida["cliente_id"] == "3"
        assert partida["cliente_nombre"] == "ACME"
        assert partida["orden_ref"] == "INV-1"
        assert partida["monto_total"] == Decimal("100.0")
        assert partida["monto_pendiente"] == Decimal("40.0")
        assert partida["dias_vencida"] == 45
        assert partida["vencida"] is True
        assert partida["bucket"] == "31_60"

        with patch("xmlrpc.client.ServerProxy", return_value=mock_proxy_instance):
            todas = connector.pull_cartera_vencida(solo_vencidas=False)
        assert len(todas) == 3
        sin_fecha = [p for p in todas if p["orden_ref"] == "INV-3"][0]
        assert sin_fecha["dias_vencida"] is None
        assert sin_fecha["vencida"] is False
        assert sin_fecha["bucket"] == "sin_fecha"

    def test_pull_cartera_vencida_error_rpc_retorna_vacio(self, settings):
        settings.DEBUG = True
        connector = _connector(config={"host": "http://l:8069", "db": "d", "uid": 2})
        mock_proxy_instance = MagicMock()
        mock_proxy_instance.execute_kw.side_effect = RuntimeError("rpc roto")
        with patch("xmlrpc.client.ServerProxy", return_value=mock_proxy_instance):
            # El except interno degrada a records=[] → lista vacía
            assert connector.pull_cartera_vencida() == []

    def test_pull_pagos_cliente_normaliza(self, settings):
        settings.DEBUG = True
        connector = _connector(config={"host": "http://l:8069", "db": "d", "uid": 2})
        mock_proxy_instance = MagicMock()
        mock_proxy_instance.execute_kw.return_value = [
            {
                "id": 9,
                "name": "PAGO-9",
                "date": "2024-03-20",
                "amount": 150.0,
                "currency_id": [2, "USD"],
                "payment_type": "inbound",
                "ref": "abono",
            }
        ]
        with patch("xmlrpc.client.ServerProxy", return_value=mock_proxy_instance):
            pagos = connector.pull_pagos_cliente("3")

        assert pagos == [
            {
                "pago_id": "9",
                "referencia": "PAGO-9",
                "fecha": "2024-03-20",
                "monto": Decimal("150.0"),
                "moneda": "USD",
                "tipo": "inbound",
                "nota": "abono",
            }
        ]

    def test_pull_pagos_cliente_error_lanza_connectionerror(self, settings):
        settings.DEBUG = True
        connector = _connector(config={"host": "http://l:8069", "db": "d", "uid": 2})
        with patch("xmlrpc.client.ServerProxy", side_effect=RuntimeError("caído")):
            with pytest.raises(ConnectorConnectionError):
                connector.pull_pagos_cliente("3")


class TestConnectorUtilidades:
    @pytest.mark.parametrize(
        "dias,bucket",
        [
            (-5, "al_dia"),
            (0, "al_dia"),
            (1, "1_30"),
            (30, "1_30"),
            (31, "31_60"),
            (60, "31_60"),
            (61, "61_90"),
            (90, "61_90"),
            (91, "mas_90"),
            (365, "mas_90"),
        ],
    )
    def test_aging_bucket(self, dias, bucket):
        assert OdooConnector._aging_bucket(dias) == bucket

    @pytest.mark.parametrize(
        "nombre,dias",
        [
            ("30 días", 30),
            ("Net 15", 15),
            ("Inmediato", 0),
            ("", 0),
            (None, 0),
        ],
    )
    def test_term_days_map(self, nombre, dias):
        assert OdooConnector._term_days_map(nombre) == dias


class TestNormalizeOdooHost:
    """normalize_odoo_host — saneo de la URL base de Odoo.

    Vive bajo tests/ (lo que ejecuta el CI) para que estas ramas cuenten en la
    cobertura del gate diff-cover; complementa los tests in-app.
    """

    @pytest.mark.parametrize(
        "raw,esperado",
        [
            # Bug real: el usuario pega la URL de login del navegador.
            (
                "https://lixie-dev-lubrika-qa-33433878.dev.odoo.com/en/web/login",
                "https://lixie-dev-lubrika-qa-33433878.dev.odoo.com",
            ),
            ("miempresa.odoo.com", "https://miempresa.odoo.com"),  # sin esquema → https
            ("miempresa.odoo.com/en/web/login", "https://miempresa.odoo.com"),
            ("https://x.odoo.com/web/login?db=foo#bar", "https://x.odoo.com"),
            ("http://localhost:8069/web", "http://localhost:8069"),  # conserva puerto/http
            ("https://x.odoo.com/", "https://x.odoo.com"),
            ("https://x.odoo.com", "https://x.odoo.com"),  # idempotente
            ("  https://x.odoo.com/web  ", "https://x.odoo.com"),  # espacios
            ("", ""),  # vacío → rama return ""
            ("   ", ""),  # solo espacios → vacío
            ("https:///ruta/", "https:///ruta"),  # sin netloc → fallback rstrip
        ],
    )
    def test_normaliza(self, raw, esperado):
        from apps.integration_hub.connectors.odoo.client import normalize_odoo_host

        assert normalize_odoo_host(raw) == esperado


class TestOdoo18PagosYReconciliacionesBatch:
    """Tests para fields_get cacheado en get_pagos y get_reconciliaciones_pagos batch (Odoo 18)."""

    def test_get_pagos_odoo18_omite_ref_y_cachea_fields_get(self):
        client, mock_models = _make_client()
        odoo18_fields = {
            "id": {"string": "ID"},
            "name": {"string": "Number"},
            "partner_id": {"string": "Partner"},
            "payment_type": {"string": "Payment Type"},
            "partner_type": {"string": "Partner Type"},
            "amount": {"string": "Amount"},
            "date": {"string": "Date"},
            "state": {"string": "Status"},
            "journal_id": {"string": "Journal"},
            "currency_id": {"string": "Currency"},
            "memo": {"string": "Memo"},
            "payment_reference": {"string": "Payment Reference"},
            "move_id": {"string": "Journal Entry"},
            "reconciled_invoice_ids": {"string": "Reconciled Invoices"},
            "reconciled_bill_ids": {"string": "Reconciled Bills"},
            "write_date": {"string": "Write Date"},
            "create_date": {"string": "Create Date"},
        }
        mock_models.execute_kw.side_effect = [
            odoo18_fields,  # 1er fields_get
            [{"id": 1, "name": "P1"}],  # 1er search_read
            [{"id": 2, "name": "P2"}],  # 2do search_read (reusa cache sin llamar fields_get!)
        ]

        res1 = client.get_pagos(tipo="inbound")
        res2 = client.get_pagos(tipo="outbound")

        assert len(res1) == 1 and len(res2) == 1
        assert mock_models.execute_kw.call_count == 3
        first_search_kwargs = mock_models.execute_kw.call_args_list[1][0][6]
        assert "ref" not in first_search_kwargs["fields"]
        assert "memo" in first_search_kwargs["fields"]
        assert "payment_reference" in first_search_kwargs["fields"]
        assert "move_id" in first_search_kwargs["fields"]
        assert "reconciled_bill_ids" in first_search_kwargs["fields"]

    def test_get_pagos_odoo_legacy_incluye_ref(self):
        client, mock_models = _make_client()
        legacy_fields = {
            "id": {"string": "ID"},
            "name": {"string": "Name"},
            "partner_id": {"string": "Partner"},
            "payment_type": {"string": "Payment Type"},
            "partner_type": {"string": "Partner Type"},
            "amount": {"string": "Amount"},
            "date": {"string": "Date"},
            "state": {"string": "Status"},
            "journal_id": {"string": "Journal"},
            "currency_id": {"string": "Currency"},
            "ref": {"string": "Reference"},
            "move_id": {"string": "Move"},
            "reconciled_invoice_ids": {"string": "Invoices"},
        }
        mock_models.execute_kw.side_effect = [legacy_fields, []]
        client.get_pagos()
        search_kwargs = mock_models.execute_kw.call_args_list[1][0][6]
        assert "ref" in search_kwargs["fields"]
        assert "memo" not in search_kwargs["fields"]

    def test_get_reconciliaciones_pagos_vacio_sin_llamadas(self):
        client, mock_models = _make_client()
        assert client.get_reconciliaciones_pagos([]) == {}
        mock_models.execute_kw.assert_not_called()

    def test_get_reconciliaciones_pagos_batch_inbound_y_outbound(self):
        client, mock_models = _make_client()
        mock_models.execute_kw.side_effect = [
            # 1. account.move.line de pagos
            [
                {
                    "id": 1001,
                    "move_id": [100, "PAY/IN/1"],
                    "account_type": "asset_receivable",
                    "matched_debit_ids": [501, 502],
                    "matched_credit_ids": [],
                    "currency_id": [2, "USD"],
                },
                {
                    "id": 1002,
                    "move_id": [200, "PAY/OUT/1"],
                    "account_type": "liability_payable",
                    "matched_debit_ids": [],
                    "matched_credit_ids": [503, 504],
                    "currency_id": [2, "USD"],
                },
            ],
            # 2. account.partial.reconcile batch read
            [
                {
                    "id": 501,
                    "debit_move_id": [2001, "INV/1"],
                    "credit_move_id": [1001, "PAY/IN/1"],
                    "amount": 35.0,
                    "debit_amount_currency": 35.0,
                    "credit_amount_currency": 35.0,
                    "debit_currency_id": [2, "USD"],
                    "credit_currency_id": [2, "USD"],
                },
                {
                    "id": 502,
                    "debit_move_id": [2002, "INV/2"],
                    "credit_move_id": [1001, "PAY/IN/1"],
                    "amount": 65.0,
                    "debit_amount_currency": 65.0,
                    "credit_amount_currency": 65.0,
                    "debit_currency_id": [2, "USD"],
                    "credit_currency_id": [2, "USD"],
                },
                {
                    "id": 503,
                    "debit_move_id": [1002, "PAY/OUT/1"],
                    "credit_move_id": [2003, "BILL/1"],
                    "amount": 120.0,
                    "debit_amount_currency": 120.0,
                    "credit_amount_currency": 120.0,
                    "debit_currency_id": [2, "USD"],
                    "credit_currency_id": [2, "USD"],
                },
                {
                    # Asiento contable no factura ('entry') debe filtrarse
                    "id": 504,
                    "debit_move_id": [1002, "PAY/OUT/1"],
                    "credit_move_id": [2004, "MISC/1"],
                    "amount": 10.0,
                    "debit_amount_currency": 10.0,
                    "credit_amount_currency": 10.0,
                    "debit_currency_id": [2, "USD"],
                    "credit_currency_id": [2, "USD"],
                },
            ],
            # 3. account.move.line contrapartes batch read
            [
                {"id": 2001, "move_id": [301, "INV/1"], "currency_id": [2, "USD"]},
                {"id": 2002, "move_id": [302, "INV/2"], "currency_id": [2, "USD"]},
                {"id": 2003, "move_id": [303, "BILL/1"], "currency_id": [2, "USD"]},
                {"id": 2004, "move_id": [304, "MISC/1"], "currency_id": [2, "USD"]},
            ],
            # 4. account.move contrapartes batch read
            [
                {"id": 301, "move_type": "out_invoice", "name": "INV/1", "currency_id": [2, "USD"]},
                {"id": 302, "move_type": "out_invoice", "name": "INV/2", "currency_id": [2, "USD"]},
                {"id": 303, "move_type": "in_invoice", "name": "BILL/1", "currency_id": [2, "USD"]},
                {"id": 304, "move_type": "entry", "name": "MISC/1", "currency_id": [2, "USD"]},
            ],
        ]

        res = client.get_reconciliaciones_pagos([100, 200])

        assert mock_models.execute_kw.call_count == 4  # batch estricto, cero N+1
        assert len(res[100]) == 2
        assert res[100][0]["move_id_externo"] == "301"
        assert res[100][0]["monto_pago"] == Decimal("35.0")
        assert res[100][1]["move_id_externo"] == "302"
        assert res[100][1]["monto_documento"] == Decimal("65.0")
        assert len(res[200]) == 1
        assert res[200][0]["move_id_externo"] == "303"
        assert res[200][0]["move_type"] == "in_invoice"
        assert res[200][0]["monto_documento"] == Decimal("120.0")

    def test_connector_pull_pagos_adjunta_reconciliaciones_y_cambia_checksum(self):
        connector, mock_client = _connector_con_cliente_mock()
        raw_pay = {
            "id": 77,
            "name": "PAY/77",
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": [8, "Prov"],
            "amount": 120.0,
            "date": "2024-06-01",
            "state": "in_process",
            "journal_id": [1, "Banco"],
            "currency_id": [2, "USD"],
            "payment_reference": "Transferencia #88",
            "move_id": [200, "PAY/77"],
            "reconciled_invoice_ids": [],
            "reconciled_bill_ids": [303],
        }
        mock_client.get_pagos.return_value = [raw_pay]
        mock_client.get_reconciliaciones_pagos.return_value = {
            200: [
                {
                    "partial_reconcile_id": 503,
                    "move_id_externo": "303",
                    "move_type": "in_invoice",
                    "monto_base": Decimal("120.0"),
                    "monto_pago": Decimal("120.0"),
                    "monto_documento": Decimal("120.0"),
                    "moneda_pago": "USD",
                    "moneda_documento": "USD",
                }
            ]
        }

        pagos = connector.pull_pagos()
        assert len(pagos) == 1
        p = pagos[0]
        assert p["facturas_externas"] == ["303"]
        assert p["referencia"] == "Transferencia #88"
        assert len(p["reconciliaciones"]) == 1
        assert p["reconciliaciones"][0]["partial_reconcile_id"] == "503"
        # Checksum incluye reconciliaciones cuando existen
        sin_recons = connector._normalizar_pago(raw_pay, reconciliaciones=None)
        assert p["_checksum"] != sin_recons["_checksum"]

    def test_helpers_defensivos_fields_sin_id_y_reconciliaciones_incompletas(self):
        client, mock_models = _make_client()

        # Helpers _m2o_id, _m2o_name, _to_decimal y recreación lazy de _fields_cache
        assert client._m2o_id("no-num") is None
        assert client._m2o_name(None) == ""
        assert client._to_decimal(None) == Decimal("0")
        assert client._to_decimal("invalido") == Decimal("0")
        delattr(client, "_fields_cache")
        mock_models.execute_kw.side_effect = [
            {"name": {"string": "N"}, "memo": {"string": "Memo"}},  # sin "id" -> rama else l.620
            [],
        ]
        assert client.get_pagos() == []
        search_kwargs = mock_models.execute_kw.call_args_list[1][0][6]
        assert "memo" in search_kwargs["fields"]
        assert "id" in search_kwargs["fields"]

        # get_reconciliaciones_pagos: aml sin id, counterpart_line sin move_id -> {}
        mock_models.execute_kw.side_effect = [
            [
                {"id": None, "move_id": [1, "X"], "matched_debit_ids": [1]},
                {"id": 10, "move_id": [100, "P"], "matched_debit_ids": [50], "matched_credit_ids": []},
            ],
            [{"id": 50, "debit_move_id": [20, "C"], "credit_move_id": [10, "P"], "amount": 5.0}],
            [{"id": 20, "move_id": False}],
        ]
        assert client.get_reconciliaciones_pagos([100]) == {}

        # get_reconciliaciones_pagos: pr duplicado / faltantes en lookup
        mock_models.execute_kw.side_effect = [
            [{"id": 10, "move_id": [100, "P"], "matched_debit_ids": [51, 52], "matched_credit_ids": []}],
            [
                {"id": None, "debit_move_id": [20, "C"], "credit_move_id": [10, "P"], "amount": 5.0},
                {"id": 51, "debit_move_id": [99, "NO_AML"], "credit_move_id": [10, "P"], "amount": 5.0},
                {"id": 52, "debit_move_id": [21, "C2"], "credit_move_id": [10, "P"], "amount": 5.0},
                {"id": 52, "debit_move_id": [21, "C2"], "credit_move_id": [10, "P"], "amount": 5.0},
            ],
            [{"id": 21, "move_id": [301, "F1"]}, {"id": 99, "move_id": [399, "F_MISSING"]}],
            [{"id": 301, "move_type": "out_invoice", "name": "F1", "currency_id": [2, "USD"]}],
        ]
        res = client.get_reconciliaciones_pagos([100])
        assert len(res[100]) == 1

        # _normalizar_pago agrega move_id_externo de reconciliaciones aunque no esté en reconciled_*_ids
        connector, _ = _connector_con_cliente_mock()
        norm = connector._normalizar_pago(
            {
                "id": 88,
                "name": "PAY/88",
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": [5, "Cli"],
                "amount": 50.0,
                "date": "2024-06-02",
                "state": "paid",
                "journal_id": [1, "B"],
                "currency_id": [2, "USD"],
                "reconciled_invoice_ids": [],
                "reconciled_bill_ids": [],
            },
            reconciliaciones=[
                {
                    "partial_reconcile_id": 900,
                    "move_id_externo": "404",
                    "move_type": "out_invoice",
                    "monto_base": Decimal("50"),
                    "monto_pago": Decimal("50"),
                    "monto_documento": Decimal("50"),
                    "moneda_pago": "USD",
                    "moneda_documento": "USD",
                }
            ],
        )
        assert norm["facturas_externas"] == ["404"]
