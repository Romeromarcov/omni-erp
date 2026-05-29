"""
Fuente 3: bcv.org.ve scraping
Usa httpx con verify=False (SSL workaround conocido con BCV).
BeautifulSoup → div#dolar > strong
Regex fallback si no encuentra el elemento.
"""
import logging
import re
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_RE_USD = re.compile(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2,4})")

def fetch_tasa_bcv() -> Decimal | None:
    try:
        resp = httpx.get(
            "https://www.bcv.org.ve/",
            verify=False,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Método directo
        el = soup.select_one("div#dolar strong")
        if el:
            txt = el.get_text(strip=True).replace(",", ".")
            return Decimal(txt)

        # Regex fallback
        m = _RE_USD.search(resp.text)
        if m:
            txt = m.group(1).replace(",", ".")
            return Decimal(txt)

    except Exception as exc:
        logger.warning("bcv_scrape falló: %s", exc)
    return None
