"""
Fuente 3 (fallback): bcv.org.ve scraping.

H-SEC-3: la verificación TLS es OBLIGATORIA por default. Una tasa BCV
inyectada por MITM contamina factura + contabilidad + SENIAT, así que NO se
usa ``verify=False``. Si el sitio del BCV rota su cadena de certificados y
falla la verificación con el bundle del sistema, se puede apuntar a una CA
empaquetada vía ``BCV_CA_BUNDLE`` (ruta a un .pem). Solo como último recurso
operativo explícito y auditado, ``BCV_SCRAPE_INSECURE=true`` desactiva la
verificación (se loguea una advertencia ruidosa en cada llamada).

BeautifulSoup → div#dolar > strong, con regex de fallback.
"""
import logging
import os
import re
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_RE_USD = re.compile(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2,4})")

# Cota de cordura: una tasa VES/USD fuera de este rango es claramente inválida
# (parsing roto o valor manipulado). Evita propagar basura aguas abajo.
_MIN_TASA = Decimal("1")
_MAX_TASA = Decimal("100000")


def _resolve_verify():
    """Resuelve el parámetro ``verify`` de httpx desde el entorno (seguro por default)."""
    bundle = os.environ.get("BCV_CA_BUNDLE")
    if bundle:
        return bundle
    if os.environ.get("BCV_SCRAPE_INSECURE", "false").lower() in ("true", "1", "yes"):
        logger.warning(
            "bcv_scrape: verificación TLS DESACTIVADA por BCV_SCRAPE_INSECURE. "
            "Riesgo de MITM en la tasa BCV — usar solo temporalmente."
        )
        return False
    return True


def _validar_tasa(valor: str) -> Decimal | None:
    try:
        tasa = Decimal(valor)
    except (InvalidOperation, ValueError):
        return None
    if not (_MIN_TASA <= tasa <= _MAX_TASA):
        logger.warning("bcv_scrape: tasa fuera de rango razonable, descartada: %s", tasa)
        return None
    return tasa


def fetch_tasa_bcv() -> Decimal | None:
    try:
        resp = httpx.get(
            "https://www.bcv.org.ve/",
            verify=_resolve_verify(),
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Método directo
        el = soup.select_one("div#dolar strong")
        if el:
            tasa = _validar_tasa(el.get_text(strip=True).replace(",", "."))
            if tasa is not None:
                return tasa

        # Regex fallback
        m = _RE_USD.search(resp.text)
        if m:
            return _validar_tasa(m.group(1).replace(",", "."))

    except Exception as exc:
        logger.warning("bcv_scrape falló: %s", exc)
    return None
