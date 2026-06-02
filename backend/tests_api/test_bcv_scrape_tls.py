"""H-SEC-3: verificación TLS obligatoria en el scrape del BCV."""

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx


def _html_resp(html):
    resp = MagicMock()
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


def test_verifica_tls_por_default():
    """Sin env de escape, httpx.get se invoca con verify=True."""
    os.environ.pop("BCV_CA_BUNDLE", None)
    os.environ.pop("BCV_SCRAPE_INSECURE", None)
    resp = _html_resp('<html><div id="dolar"><strong>36,50</strong></div></html>')
    with patch("httpx.get", return_value=resp) as mock_get:
        from apps.integration_hub.connectors.tasas_ve.sources import bcv_scrape

        assert bcv_scrape.fetch_tasa_bcv() == Decimal("36.50")
    assert mock_get.call_args.kwargs["verify"] is True


def test_falla_certificado_invalido_retorna_none():
    """Un error TLS (cert inválido) no propaga tasa — retorna None."""
    with patch("httpx.get", side_effect=httpx.ConnectError("certificate verify failed")):
        from apps.integration_hub.connectors.tasas_ve.sources import bcv_scrape

        assert bcv_scrape.fetch_tasa_bcv() is None


def test_tasa_fuera_de_rango_descartada():
    """Una tasa absurda (parsing roto / manipulada) se descarta."""
    resp = _html_resp('<html><div id="dolar"><strong>0,00</strong></div></html>')
    with patch("httpx.get", return_value=resp):
        from apps.integration_hub.connectors.tasas_ve.sources import bcv_scrape

        assert bcv_scrape.fetch_tasa_bcv() is None


def test_ca_bundle_env_se_pasa_a_verify():
    """BCV_CA_BUNDLE se propaga como ruta en verify."""
    resp = _html_resp('<html><div id="dolar"><strong>36,50</strong></div></html>')
    with patch.dict(os.environ, {"BCV_CA_BUNDLE": "/etc/ssl/bcv-chain.pem"}):
        with patch("httpx.get", return_value=resp) as mock_get:
            from apps.integration_hub.connectors.tasas_ve.sources import bcv_scrape

            bcv_scrape.fetch_tasa_bcv()
    assert mock_get.call_args.kwargs["verify"] == "/etc/ssl/bcv-chain.pem"
