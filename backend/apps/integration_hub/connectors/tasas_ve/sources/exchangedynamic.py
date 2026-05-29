"""
Fuente 2: api.exchangedynamic.com
GET https://api.exchangedynamic.com/v1/rates?base=USD&target=VES
Retorna Decimal o None.
"""
import logging
from decimal import Decimal
import httpx

logger = logging.getLogger(__name__)

def fetch_tasa_bcv() -> Decimal | None:
    try:
        resp = httpx.get(
            "https://api.exchangedynamic.com/v1/rates",
            params={"base": "USD", "target": "VES"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data.get("rates", {}).get("VES") or data.get("rate")
        if rate:
            return Decimal(str(rate))
    except Exception as exc:
        logger.warning("exchangedynamic falló: %s", exc)
    return None
