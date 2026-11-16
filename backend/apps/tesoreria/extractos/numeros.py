"""Normalización determinística de montos, fechas y referencias de extractos bancarios.

Soporta formatos mixtos de la banca venezolana e internacional:
- Montos con coma decimal y punto de miles (``1.002.945,86``), punto decimal y coma de
  miles (``58,509.32``), negativos contables entre paréntesis (``(54,00)``), enteros y
  flotantes provenientes de hojas de cálculo (sin arrastrar ruido binario IEEE-754).
- Fechas ISO, ``dd/mm/YYYY``, ``dd-mm-YYYY``, ``dd/mm/yy`` (portales web bancarios) y
  seriales numéricos de Excel (sistemas 1900 y 1904).
- Referencias numéricas o con apóstrofe inicial (``'19763674``, ``640065766.0``).
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")


def parse_monto(valor: Any, *, punto_miles: bool = True) -> Decimal | None:
    """Convierte un valor crudo de celda a ``Decimal`` redondeado a 2 decimales.

    Devuelve ``None`` si la celda está vacía. Rechaza booleanos, ``NaN``/``Inf`` y
    textos no numéricos con ``ValueError``. Cuando ``punto_miles=False`` (p. ej.
    exportaciones anglosajonas/cripto como Binance), un único ``.`` con 3 decimales
    (``1.250``) se interpreta siempre como separador decimal y nunca de miles.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError(f"Monto inválido: {valor!r}")
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ValueError(f"Monto inválido: {valor!r}")
        try:
            return valor.quantize(CENT)
        except InvalidOperation as exc:
            raise ValueError(f"Monto inválido: {valor!r}") from exc
    if isinstance(valor, int):
        try:
            return Decimal(valor).quantize(CENT)
        except InvalidOperation as exc:
            raise ValueError(f"Monto inválido: {valor!r}") from exc
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ValueError(f"Monto inválido: {valor!r}")
        try:
            return Decimal(repr(valor)).quantize(CENT)
        except InvalidOperation as exc:
            raise ValueError(f"Monto inválido: {valor!r}") from exc

    s = str(valor).replace("\x00", "").strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()+")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        mil = "." if dec == "," else ","
        s = s.replace(mil, "").replace(dec, ".")
    elif "," in s:
        # Solo coma: separador de miles únicamente cuando inicia en 1..9 y agrupa de a 3.
        if re.search(r"^[1-9]\d{0,2}(,\d{3})+$", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif s.count(".") > 1 or (punto_miles and re.search(r"^[1-9]\d{0,2}\.\d{3}$", s)):
        # '1.002.945' o '1.234': punto de miles en extractos bancarios sin decimales.
        # Jamás aplica a '0.xxx' ni cuando punto_miles=False (p. ej. Binance '1.250').
        s = s.replace(".", "")

    try:
        crudo = Decimal(s)
        if not crudo.is_finite():
            raise ValueError(f"Monto inválido: {valor!r}")
        d = crudo.quantize(CENT)
    except InvalidOperation as exc:
        raise ValueError(f"Monto inválido: {valor!r}") from exc
    return -d if neg else d


def parse_fecha(valor: Any, datemode: int = 0) -> date:
    """Convierte un valor de celda a ``datetime.date``."""
    if isinstance(valor, bool):
        raise ValueError(f"Fecha inválida: {valor!r}")
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, int | float):
        dias = float(valor)
        if not math.isfinite(dias):
            raise ValueError(f"Fecha inválida: {valor!r}")
        base = datetime(1899, 12, 30) if datemode == 0 else datetime(1904, 1, 1)
        try:
            return (base + timedelta(days=dias)).date()
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Fecha inválida: {valor!r}") from exc

    s = str(valor).replace("\x00", "").strip()
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2}", s):
        return datetime.strptime(s, "%d/%m/%y").date()
    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: {valor!r}")


def limpiar_ref(valor: Any) -> str:
    """Normaliza referencias bancarias eliminando apóstrofes de Excel y ``.0`` finales."""
    if valor is None or valor == "" or isinstance(valor, bool):
        return ""
    if isinstance(valor, float):
        if not math.isfinite(valor):
            return ""
        if valor.is_integer():
            return str(int(valor))
    texto = str(valor).replace("\x00", "").strip().lstrip("'").strip()
    if re.fullmatch(r"\d+\.0+", texto):
        return texto.split(".", 1)[0]
    return texto

