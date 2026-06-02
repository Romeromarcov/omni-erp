"""H-BUG-3: el OdooConnector devuelve montos como Decimal (no float)."""

from decimal import Decimal
from unittest.mock import MagicMock, patch


def _connector():
    from apps.integration_hub.connectors.odoo.connector import OdooConnector

    c = OdooConnector.__new__(OdooConnector)
    # https para satisfacer M-SEC-2 (DEBUG=False bajo el test runner de Django).
    c._config = {"url": "https://odoo.example.com", "db": "test", "uid": 1, "password": "x"}
    return c


def test_safe_decimal_no_hereda_error_binario():
    c = _connector()
    # 0.1 + 0.2 con Decimal vía str no produce 0.30000000000000004
    assert c._safe_decimal("0.1") + c._safe_decimal("0.2") == Decimal("0.3")
    assert c._safe_decimal(None) == Decimal("0")
    assert c._safe_decimal(False) == Decimal("0")
    assert c._safe_decimal("basura") == Decimal("0")


def test_pull_cartera_vencida_devuelve_decimal():
    c = _connector()
    fake_proxy = MagicMock()
    fake_proxy.execute_kw.return_value = [
        {
            "partner_id": [5, "Cliente X"],
            "name": "INV/001",
            "amount_total": 100.1,
            "amount_residual": 50.2,
            "invoice_date_due": "2020-01-01",
        }
    ]
    with patch("xmlrpc.client.ServerProxy", return_value=fake_proxy):
        rows = c.pull_cartera_vencida(solo_vencidas=False)
    assert rows, "esperaba al menos una fila"
    assert isinstance(rows[0]["monto_total"], Decimal)
    assert isinstance(rows[0]["monto_pendiente"], Decimal)
    assert rows[0]["monto_total"] == Decimal("100.1")


def test_pull_cartera_dias_vencida_none_si_fecha_invalida():
    """M-BUG-15: sin fecha de vencimiento, dias_vencida es None (no 0)."""
    c = _connector()
    fake_proxy = MagicMock()
    fake_proxy.execute_kw.return_value = [
        {"partner_id": [5, "Cliente X"], "name": "INV/002", "amount_total": 10, "amount_residual": 10}
    ]
    with patch("xmlrpc.client.ServerProxy", return_value=fake_proxy):
        rows = c.pull_cartera_vencida(solo_vencidas=False)
    assert rows[0]["dias_vencida"] is None
    assert rows[0]["bucket"] == "sin_fecha"
