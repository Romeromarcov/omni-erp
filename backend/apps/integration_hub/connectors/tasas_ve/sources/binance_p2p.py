"""
Binance P2P: 5 BUY + 5 SELL → promedio de 10 precios.
Persiste como PROMEDIO_MERCADO en finanzas.TasaCambio.
"""
import logging
from decimal import Decimal
import httpx

logger = logging.getLogger(__name__)

BINANCE_P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

def _fetch_side(trade_type: str, rows: int = 5) -> list[Decimal]:
    payload = {
        "fiat": "VES",
        "page": 1,
        "rows": rows,
        "tradeType": trade_type,
        "asset": "USDT",
        "countries": [],
        "proMerchantAds": False,
        "publisherType": None,
    }
    try:
        resp = httpx.post(BINANCE_P2P_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [Decimal(str(item["adv"]["price"])) for item in data if item.get("adv", {}).get("price")]
    except Exception as exc:
        logger.warning("binance_p2p %s falló: %s", trade_type, exc)
        return []


def fetch_tasa_binance_p2p() -> Decimal | None:
    """Promedio de 5 BUY + 5 SELL. Retorna None si no hay datos suficientes."""
    compras = _fetch_side("BUY", 5)
    ventas = _fetch_side("SELL", 5)
    todos = compras + ventas
    if not todos:
        return None
    return sum(todos) / Decimal(len(todos))
