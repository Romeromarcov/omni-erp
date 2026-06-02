"""
M10-T6: Validadores venezolanos.

RIF:  Registro de Información Fiscal
      Formato: J-XXXXXXXX-D  (J/V/E/G/P + 8 dígitos + dígito verificador)
CI:   Cédula de Identidad
      Formato: V-XXXXXXXX  (V/E + hasta 8 dígitos)
NroCtrl: Número de control SENIAT
      Formato: 00-XXXXXXXX  (2 dígitos + guion + hasta 8 dígitos)
"""

from __future__ import annotations

import re


# ── Constantes ────────────────────────────────────────────────────────────────

RIF_PATTERN = re.compile(r"^([JVEGP])-?(\d{8})-?(\d)$", re.IGNORECASE)
CI_PATTERN = re.compile(r"^([VE])-?(\d{1,8})$", re.IGNORECASE)
NRO_CTRL_PATTERN = re.compile(r"^(\d{2})-(\d{1,8})$")

# Pesos para el dígito verificador del RIF
_PESOS_RIF = [4, 3, 2, 7, 6, 5, 4, 3, 2]


# ── Validador de RIF ──────────────────────────────────────────────────────────


def validar_rif(rif: str) -> bool:
    """
    Valida el FORMATO de un RIF venezolano.

    Verifica que tenga el patrón correcto: tipo (J/V/E/G/P) + 8 dígitos + dígito verificador.
    No valida el dígito de control matemáticamente (ver `verificar_digito_rif` para eso).

    Args:
        rif: RIF en formato J-12345678-9 o J123456789 (con o sin guiones).

    Returns:
        True si el formato es válido.

    Examples:
        >>> validar_rif("J-30543012-5")
        True
        >>> validar_rif("V-12345678-3")
        True
        >>> validar_rif("X-12345678-5")
        False
        >>> validar_rif("12345678")
        False
    """
    if not rif:
        return False
    return bool(RIF_PATTERN.match(rif.strip().upper()))


def verificar_digito_rif(rif: str) -> bool:
    """
    Verifica el dígito de control matemático de un RIF venezolano.

    Implementa el algoritmo de pesos de SENIAT:
    - Factor tipo: J=0, V=1, E=2, G=3, P=4
    - Pesos: [4, 3, 2, 7, 6, 5, 4, 3, 2] para [tipo, d1..d8]
    - DV = 11 - (suma % 11), excepto si resto=0→DV=0, resto=1→DV=0

    Args:
        rif: RIF con formato válido.

    Returns:
        True si el dígito verificador es correcto.
    """
    if not rif:
        return False

    match = RIF_PATTERN.match(rif.strip().upper())
    if not match:
        return False

    tipo, numero, digito_verificador = match.groups()
    digitos = numero.zfill(8)

    factores = {"J": 0, "V": 1, "E": 2, "G": 3, "P": 4}
    factor_tipo = factores.get(tipo.upper(), 0)

    suma = factor_tipo * _PESOS_RIF[0]
    for i, d in enumerate(digitos):
        suma += int(d) * _PESOS_RIF[i + 1]

    resto = suma % 11
    if resto in (0, 1):
        dv_calculado = 0
    else:
        dv_calculado = 11 - resto

    return int(digito_verificador) == dv_calculado


def normalizar_rif(rif: str) -> str:
    """
    Normaliza un RIF al formato estándar J-XXXXXXXX-D.

    Args:
        rif: RIF en cualquier formato válido.

    Returns:
        RIF normalizado, ej. "J-30543012-5".

    Raises:
        ValueError: Si el RIF tiene formato incorrecto.
    """
    if not rif:
        raise ValueError("RIF vacío")
    match = RIF_PATTERN.match(rif.strip().upper())
    if not match:
        raise ValueError(f"Formato de RIF inválido: {rif!r}")
    tipo, numero, dv = match.groups()
    return f"{tipo.upper()}-{numero.zfill(8)}-{dv}"


# ── Validador de Cédula ───────────────────────────────────────────────────────


def validar_cedula(cedula: str) -> bool:
    """
    Valida el formato de una cédula de identidad venezolana.

    Formato esperado: V-12345678 o E-12345678 (con o sin guion).
    Nota: No valida existencia real en el CNE.

    Args:
        cedula: Cédula en formato V-XXXXXXXX o VXXXXXXXX.

    Returns:
        True si el formato es válido.
    """
    if not cedula:
        return False
    return bool(CI_PATTERN.match(cedula.strip().upper()))


def normalizar_cedula(cedula: str) -> str:
    """
    Normaliza una cédula al formato V-XXXXXXXX.

    Raises:
        ValueError: Si el formato es incorrecto.
    """
    if not cedula:
        raise ValueError("Cédula vacía")
    match = CI_PATTERN.match(cedula.strip().upper())
    if not match:
        raise ValueError(f"Formato de cédula inválido: {cedula!r}")
    tipo, numero = match.groups()
    return f"{tipo.upper()}-{numero.zfill(8)}"


# ── Validador de Número de Control SENIAT ────────────────────────────────────


def validar_numero_control(numero_ctrl: str) -> bool:
    """
    Valida el formato del número de control SENIAT.

    Formato: 00-XXXXXXXX (2 dígitos + guión + hasta 8 dígitos).

    Args:
        numero_ctrl: Número de control, ej. "00-00000123".

    Returns:
        True si el formato es válido.
    """
    if not numero_ctrl:
        return False
    return bool(NRO_CTRL_PATTERN.match(numero_ctrl.strip()))


def siguiente_numero_control(ultimo: str) -> str:
    """
    Calcula el siguiente número de control SENIAT en secuencia.

    Args:
        ultimo: Último número emitido, ej. "00-00000099".

    Returns:
        Siguiente número, ej. "00-00000100".

    Raises:
        ValueError: Si el formato es incorrecto.
    """
    match = NRO_CTRL_PATTERN.match(ultimo.strip())
    if not match:
        raise ValueError(f"Número de control inválido: {ultimo!r}")
    prefijo, secuencia = match.groups()
    siguiente = int(secuencia) + 1
    return f"{prefijo}-{str(siguiente).zfill(len(secuencia))}"


# ── Validador de email venezolano (básico) ────────────────────────────────────


def validar_email(email: str) -> bool:
    """Validación básica de formato de email."""
    patron = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    return bool(patron.match((email or "").strip()))
