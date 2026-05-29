"""
Fuente 1: ve.dolarapi.com
GET https://ve.dolarapi.com/v1/dolares → filtra fuente='oficial' o 'bcv'
Retorna Decimal o None si falla.
"""
import logging
from decimal import Decimal
import httpx

logger = logging.getLogger(__name__)

def fetch_tasa_bcv() -> Decimal | None:
    try:
        resp = httpx.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
        resp.raise_for_status()
        for item in resp.json():
            if item.get("fuente", "").lower() in ("oficial", "bcv"):
                return Decimal(str(item["promedio"]))
    except Exception as exc:
        logger.warning("dolarapi falló: %s", exc)
    return None
