"""
Tests para TasasVeConnector y fuentes individuales.
Usa unittest.mock para aislar llamadas HTTP reales.
"""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_response(json_data, status_code=200):
    """Crea un mock de httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_error_response():
    """Simula un httpx.get/post que lanza excepción."""
    raise Exception("Connection refused")


# ── Tests dolarapi ────────────────────────────────────────────────────────────

class TestDolarapi:
    def test_fetch_ok_fuente_oficial(self):
        data = [
            {"fuente": "oficial", "promedio": "36.50"},
            {"fuente": "paralelo", "promedio": "40.00"},
        ]
        with patch("httpx.get", return_value=_mock_response(data)):
            from apps.integration_hub.connectors.tasas_ve.sources import dolarapi
            # Reload to avoid cached import
            import importlib
            importlib.reload(dolarapi)
            result = dolarapi.fetch_tasa_bcv()
        assert result == Decimal("36.50")

    def test_fetch_ok_fuente_bcv(self):
        data = [{"fuente": "bcv", "promedio": "36.75"}]
        with patch("httpx.get", return_value=_mock_response(data)):
            from apps.integration_hub.connectors.tasas_ve.sources import dolarapi
            result = dolarapi.fetch_tasa_bcv()
        assert result == Decimal("36.75")

    def test_fetch_no_matching_fuente(self):
        data = [{"fuente": "paralelo", "promedio": "40.00"}]
        with patch("httpx.get", return_value=_mock_response(data)):
            from apps.integration_hub.connectors.tasas_ve.sources import dolarapi
            result = dolarapi.fetch_tasa_bcv()
        assert result is None

    def test_fetch_exception_returns_none(self):
        with patch("httpx.get", side_effect=Exception("timeout")):
            from apps.integration_hub.connectors.tasas_ve.sources import dolarapi
            result = dolarapi.fetch_tasa_bcv()
        assert result is None


# ── Tests exchangedynamic ─────────────────────────────────────────────────────

class TestExchangeDynamic:
    def test_fetch_ok_rates_key(self):
        data = {"rates": {"VES": "36.80"}}
        with patch("httpx.get", return_value=_mock_response(data)):
            from apps.integration_hub.connectors.tasas_ve.sources import exchangedynamic
            result = exchangedynamic.fetch_tasa_bcv()
        assert result == Decimal("36.80")

    def test_fetch_ok_rate_key(self):
        data = {"rate": "36.90"}
        with patch("httpx.get", return_value=_mock_response(data)):
            from apps.integration_hub.connectors.tasas_ve.sources import exchangedynamic
            result = exchangedynamic.fetch_tasa_bcv()
        assert result == Decimal("36.90")

    def test_fetch_exception_returns_none(self):
        with patch("httpx.get", side_effect=Exception("timeout")):
            from apps.integration_hub.connectors.tasas_ve.sources import exchangedynamic
            result = exchangedynamic.fetch_tasa_bcv()
        assert result is None


# ── Tests bcv_scrape ──────────────────────────────────────────────────────────

class TestBcvScrape:
    def test_fetch_ok_strong_element(self):
        html = '<html><div id="dolar"><strong>36,50</strong></div></html>'
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=resp):
            from apps.integration_hub.connectors.tasas_ve.sources import bcv_scrape
            result = bcv_scrape.fetch_tasa_bcv()
        assert result == Decimal("36.50")

    def test_fetch_exception_returns_none(self):
        with patch("httpx.get", side_effect=Exception("SSL error")):
            from apps.integration_hub.connectors.tasas_ve.sources import bcv_scrape
            result = bcv_scrape.fetch_tasa_bcv()
        assert result is None


# ── Tests Cascade BCV ─────────────────────────────────────────────────────────

class TestCascadeBCV:
    def test_cascade_bcv_fuente1_ok(self):
        """dolarapi responde → usa esa tasa, no consulta fuentes siguientes."""
        data_dolarapi = [{"fuente": "oficial", "promedio": "36.50"}]

        with patch(
            "apps.integration_hub.connectors.tasas_ve.sources.dolarapi.httpx.get",
            return_value=_mock_response(data_dolarapi),
        ) as mock_get:
            from apps.integration_hub.connectors.tasas_ve.connector import TasasVeConnector
            connector = TasasVeConnector()
            result = connector.pull_tasa_bcv()

        assert result == Decimal("36.50")

    def test_cascade_bcv_fuente1_falla_usa_fuente2(self):
        """dolarapi falla → exchangedynamic responde."""
        data_exchangedynamic = {"rates": {"VES": "36.80"}}

        with (
            patch(
                "apps.integration_hub.connectors.tasas_ve.sources.dolarapi.httpx.get",
                side_effect=Exception("timeout"),
            ),
            patch(
                "apps.integration_hub.connectors.tasas_ve.sources.exchangedynamic.httpx.get",
                return_value=_mock_response(data_exchangedynamic),
            ),
        ):
            from apps.integration_hub.connectors.tasas_ve.connector import TasasVeConnector
            connector = TasasVeConnector()
            result = connector.pull_tasa_bcv()

        assert result == Decimal("36.80")

    def test_cascade_bcv_todas_fallan(self):
        """Todas las fuentes fallan → retorna None."""
        with (
            patch(
                "apps.integration_hub.connectors.tasas_ve.sources.dolarapi.httpx.get",
                side_effect=Exception("timeout"),
            ),
            patch(
                "apps.integration_hub.connectors.tasas_ve.sources.exchangedynamic.httpx.get",
                side_effect=Exception("timeout"),
            ),
            patch(
                "apps.integration_hub.connectors.tasas_ve.sources.bcv_scrape.httpx.get",
                side_effect=Exception("SSL error"),
            ),
        ):
            from apps.integration_hub.connectors.tasas_ve.connector import TasasVeConnector
            connector = TasasVeConnector()
            result = connector.pull_tasa_bcv()

        assert result is None


# ── Tests Binance P2P ─────────────────────────────────────────────────────────

class TestBinanceP2P:
    def _make_binance_response(self, prices: list[str]):
        data = [{"adv": {"price": p}} for p in prices]
        return _mock_response({"data": data})

    def test_binance_p2p_promedio(self):
        """Mock 5 BUY + 5 SELL → verifica promedio correcto con Decimal."""
        buy_prices = ["36.00", "36.10", "36.20", "36.30", "36.40"]
        sell_prices = ["37.00", "37.10", "37.20", "37.30", "37.40"]
        expected = sum(Decimal(p) for p in buy_prices + sell_prices) / Decimal(10)

        buy_resp = self._make_binance_response(buy_prices)
        sell_resp = self._make_binance_response(sell_prices)

        with patch(
            "apps.integration_hub.connectors.tasas_ve.sources.binance_p2p.httpx.post",
            side_effect=[buy_resp, sell_resp],
        ):
            from apps.integration_hub.connectors.tasas_ve.sources.binance_p2p import fetch_tasa_binance_p2p
            result = fetch_tasa_binance_p2p()

        assert result == expected

    def test_binance_p2p_sin_datos_retorna_none(self):
        """Si no hay datos en ningún lado → retorna None."""
        with patch(
            "apps.integration_hub.connectors.tasas_ve.sources.binance_p2p.httpx.post",
            side_effect=Exception("connection error"),
        ):
            from apps.integration_hub.connectors.tasas_ve.sources.binance_p2p import fetch_tasa_binance_p2p
            result = fetch_tasa_binance_p2p()
        assert result is None


# ── Tests Aging Bucket ────────────────────────────────────────────────────────

class TestAgingBucket:
    def test_aging_bucket_limites(self):
        """Verifica todos los límites de buckets."""
        from apps.integration_hub.connectors.odoo.connector import OdooConnector

        assert OdooConnector._aging_bucket(0) == "al_dia"
        assert OdooConnector._aging_bucket(-5) == "al_dia"
        assert OdooConnector._aging_bucket(1) == "1_30"
        assert OdooConnector._aging_bucket(30) == "1_30"
        assert OdooConnector._aging_bucket(31) == "31_60"
        assert OdooConnector._aging_bucket(60) == "31_60"
        assert OdooConnector._aging_bucket(61) == "61_90"
        assert OdooConnector._aging_bucket(90) == "61_90"
        assert OdooConnector._aging_bucket(91) == "mas_90"
        assert OdooConnector._aging_bucket(365) == "mas_90"
