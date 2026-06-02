"""
M10-T6: Formateo de montos y textos para Venezuela.

Formateo de montos en Bs (Bolívares) y USD con el estilo local venezolano:
- Separador de miles: punto (.)
- Separador decimal: coma (,)
- Símbolo: "Bs." para bolívares, "$" para USD
"""

from __future__ import annotations

from decimal import Decimal
from typing import Union

Numero = Union[Decimal, float, int, str]


def _a_decimal(valor: Numero) -> Decimal:
    """Convierte cualquier tipo numérico a Decimal."""
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def formatear_bolivares(monto: Numero, decimales: int = 2, incluir_simbolo: bool = True) -> str:
    """
    Formatea un monto en Bolívares con el estilo venezolano.

    Ejemplos:
        >>> formatear_bolivares(1234567.89)
        'Bs. 1.234.567,89'
        >>> formatear_bolivares(1000, incluir_simbolo=False)
        '1.000,00'

    Args:
        monto:           Valor numérico a formatear.
        decimales:       Cantidad de decimales (default 2).
        incluir_simbolo: Si True, agrega "Bs." al inicio.

    Returns:
        String formateado al estilo venezolano.
    """
    valor = _a_decimal(monto)
    # Formatear con separadores internacionales primero
    formato = f"{{:,.{decimales}f}}".format(float(valor))
    # Intercambiar separadores: coma ↔ punto (estilo venezolano)
    # "1,234,567.89" → "1.234.567,89"
    resultado = formato.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
    return f"Bs. {resultado}" if incluir_simbolo else resultado


def formatear_usd(monto: Numero, decimales: int = 2, incluir_simbolo: bool = True) -> str:
    """
    Formatea un monto en USD con el estilo estándar internacional.

    Ejemplos:
        >>> formatear_usd(1234.50)
        '$ 1,234.50'

    Args:
        monto:           Valor numérico.
        decimales:       Cantidad de decimales.
        incluir_simbolo: Si True, agrega "$ " al inicio.

    Returns:
        String formateado.
    """
    valor = _a_decimal(monto)
    resultado = f"{{:,.{decimales}f}}".format(float(valor))
    return f"$ {resultado}" if incluir_simbolo else resultado


def formatear_monto(monto: Numero, codigo_moneda: str = "USD", decimales: int = 2) -> str:
    """
    Formatea un monto según el código de moneda.

    Args:
        monto:          Valor numérico.
        codigo_moneda:  "USD", "VES", "EUR", etc.
        decimales:      Decimales a mostrar.

    Returns:
        String formateado con símbolo adecuado.
    """
    codigo = (codigo_moneda or "USD").upper()
    if codigo in ("VES", "BS", "BsS", "BSF", "VEF"):
        return formatear_bolivares(monto, decimales)
    elif codigo == "USD":
        return formatear_usd(monto, decimales)
    elif codigo == "EUR":
        valor = _a_decimal(monto)
        return f"€ {float(valor):,.{decimales}f}"
    else:
        valor = _a_decimal(monto)
        return f"{codigo} {float(valor):,.{decimales}f}"


def monto_a_letras(monto: Numero, moneda: str = "DOLARES") -> str:
    """
    Convierte un monto numérico a su representación en letras (español venezolano).

    Soporta hasta 999,999,999.99.
    Útil para facturas y cheques.

    Args:
        monto:   Valor numérico (se trunca a 2 decimales).
        moneda:  Nombre de la moneda en mayúsculas (ej. "BOLIVARES", "DOLARES").

    Returns:
        String en letras, ej. "MIL DOSCIENTOS TREINTA Y CUATRO CON 50/100 DÓLARES"
    """
    valor = _a_decimal(monto)
    entero = int(valor)
    centavos = int(round((valor - entero) * 100))

    letras = _numero_a_letras(entero)
    if centavos > 0:
        return f"{letras} CON {centavos:02d}/100 {moneda}"
    return f"{letras} {moneda}"


# ── Conversión números a letras ───────────────────────────────────────────────

_UNIDADES = [
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE",
    "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE",
    "DIECIOCHO", "DIECINUEVE",
]
_DECENAS = [
    "", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA",
    "SESENTA", "SETENTA", "OCHENTA", "NOVENTA",
]
_CENTENAS = [
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
    "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
]


def _cientos(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "CIEN"
    c = n // 100
    dec = (n % 100) // 10
    uni = n % 10
    partes = []
    if c:
        partes.append(_CENTENAS[c])
    if dec == 1:
        partes.append(_UNIDADES[10 + uni])
    elif dec == 2 and uni > 0:
        partes.append(f"VEINTI{_UNIDADES[uni]}")
    else:
        if dec:
            partes.append(_DECENAS[dec])
        if uni:
            partes.append(_UNIDADES[uni])
    return " Y ".join(p for p in partes if p) if len(partes) > 1 else (partes[0] if partes else "")


def _numero_a_letras(n: int) -> str:
    if n < 0:
        return f"MENOS {_numero_a_letras(-n)}"
    if n == 0:
        return "CERO"
    if n < 1000:
        return _cientos(n)
    if n < 1_000_000:
        miles = n // 1000
        resto = n % 1000
        prefijo = "MIL" if miles == 1 else f"{_cientos(miles)} MIL"
        if resto:
            return f"{prefijo} {_cientos(resto)}"
        return prefijo
    if n < 1_000_000_000:
        millones = n // 1_000_000
        resto = n % 1_000_000
        prefijo = "UN MILLÓN" if millones == 1 else f"{_cientos(millones)} MILLONES"
        if resto:
            return f"{prefijo} {_numero_a_letras(resto)}"
        return prefijo
    return str(n)  # fallback para números muy grandes
