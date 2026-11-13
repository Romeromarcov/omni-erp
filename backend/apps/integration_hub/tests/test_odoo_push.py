"""push_pedido_venta / push_pago del OdooConnector (con cliente XML-RPC simulado; sin servidor Odoo)."""

from unittest.mock import MagicMock

import pytest

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorDataError,
    ConnectorNotSupportedError,
)
from apps.integration_hub.connectors.odoo.client import OdooXMLRPCClient
from apps.integration_hub.connectors.odoo.connector import OdooConnector


@pytest.fixture
def conn():
    c = OdooConnector.__new__(
        OdooConnector
    )  # sin instancia/BD: solo la lógica de mapeo
    c._get_client = lambda: c._cli  # type: ignore[method-assign]
    c._cli = MagicMock()
    return c


def test_pedido_venta_mapea_lineas_y_devuelve_id(conn):
    conn._cli.crear_pedido_venta.return_value = 77
    r = conn.push_pedido_venta(
        {
            "partner_id": "5",
            "referencia": "PED-1",
            "vendedor_id": 3,
            "lineas": [{"product_id": "9", "cantidad": "2", "precio": "12.50"}],
        }
    )
    assert r == "77"
    vals = conn._cli.crear_pedido_venta.call_args.args[0]
    assert (
        vals["partner_id"] == 5
        and vals["client_order_ref"] == "PED-1"
        and vals["user_id"] == 3
    )
    assert vals["order_line"] == [
        (0, 0, {"product_id": 9, "product_uom_qty": 2.0, "price_unit": 12.5})
    ]


@pytest.mark.parametrize(
    "datos", [{}, {"partner_id": 1}, {"partner_id": 1, "lineas": []}, {"lineas": [{}]}]
)
def test_pedido_venta_valida_entrada(conn, datos):
    with pytest.raises(ConnectorDataError):
        conn.push_pedido_venta(datos)


def test_pago_cliente_es_inbound_customer_en_borrador(conn):
    conn._cli.crear_pago.return_value = 501
    assert (
        conn.push_pago(
            {"partner_id": 5, "monto": "100.5", "journal_id": 2, "referencia": "REF1"}
        )
        == "501"
    )
    v = conn._cli.crear_pago.call_args.args[0]
    assert (v["payment_type"], v["partner_type"], v["amount"], v["memo"]) == (
        "inbound",
        "customer",
        100.5,
        "REF1",
    )


def test_pago_proveedor_es_outbound_supplier(conn):
    conn._cli.crear_pago.return_value = 9
    conn.push_pago({"partner_id": 5, "monto": 10, "journal_id": 2, "tipo": "proveedor"})
    v = conn._cli.crear_pago.call_args.args[0]
    assert (v["payment_type"], v["partner_type"]) == ("outbound", "supplier")


@pytest.mark.parametrize(
    "datos",
    [
        {"monto": 1, "journal_id": 1},
        {"partner_id": 1, "journal_id": 1},
        {"partner_id": 1, "monto": 1},
        {"partner_id": 1, "monto": -5, "journal_id": 1},
    ],
)
def test_pago_valida_entrada(conn, datos):
    with pytest.raises(ConnectorDataError):
        conn.push_pago(datos)


def test_cliente_crea_con_create_sin_nones():
    cli = OdooXMLRPCClient.__new__(OdooXMLRPCClient)
    cli.call = MagicMock(return_value=[12])
    assert cli.crear_pago({"amount": 1.0, "memo": None}) == 12
    assert cli.call.call_args.args == ("account.payment", "create", [{"amount": 1.0}])
    cli.call = MagicMock(return_value=33)
    assert cli.crear_pedido_venta({"partner_id": 1}) == 33


def test_base_no_soporta_push_por_defecto():
    class Dummy(BaseConnector):
        PROVIDER_NAME = "x"

        def test_connection(
            self,
        ):  # pragma: no cover - requeridos por la clase abstracta
            raise NotImplementedError

        def get_version_info(self):  # pragma: no cover
            raise NotImplementedError

    d = Dummy.__new__(Dummy)
    with pytest.raises(ConnectorNotSupportedError):
        d.push_pedido_venta({})
    with pytest.raises(ConnectorNotSupportedError):
        d.push_pago({})
