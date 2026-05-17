"""
M10-T6: Zona horaria venezolana (VET — Venezuela Standard Time).

Venezuela usa UTC-4 todo el año (sin cambio de horario desde 2007).

Uso:
    from apps.vzla_localizacion.zona_horaria import ahora_vet, a_vet, a_utc
    dt_local = ahora_vet()
    dt_utc   = a_utc(dt_local)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

# Venezuela Standard Time: UTC-4 (fijo, sin DST)
VET = timezone(timedelta(hours=-4), name="VET")
UTC = timezone.utc

# Formato estándar venezolano para facturas
FORMATO_FECHA_VE = "%d/%m/%Y"
FORMATO_DATETIME_VE = "%d/%m/%Y %H:%M"


def ahora_vet() -> datetime:
    """Retorna la fecha/hora actual en zona horaria VET (UTC-4)."""
    return datetime.now(tz=VET)


def a_vet(dt: datetime) -> datetime:
    """
    Convierte un datetime (UTC o cualquier TZ) a VET (UTC-4).

    Args:
        dt: datetime con timezone info.

    Returns:
        datetime en VET.

    Raises:
        ValueError: Si dt no tiene timezone info.
    """
    if dt.tzinfo is None:
        raise ValueError("El datetime debe tener timezone info. Use timezone.utc o similar.")
    return dt.astimezone(VET)


def a_utc(dt: datetime) -> datetime:
    """
    Convierte un datetime (VET u otra TZ) a UTC.

    Args:
        dt: datetime con timezone info.

    Returns:
        datetime en UTC.
    """
    if dt.tzinfo is None:
        raise ValueError("El datetime debe tener timezone info.")
    return dt.astimezone(UTC)


def formatear_fecha_ve(dt, solo_fecha: bool = True) -> str:
    """
    Formatea un datetime o date al formato venezolano DD/MM/YYYY.

    Args:
        dt:         datetime o date.
        solo_fecha: Si True, retorna solo DD/MM/YYYY; si False incluye hora.

    Returns:
        String formateado.
    """
    from datetime import date as DateType

    if isinstance(dt, DateType) and not isinstance(dt, datetime):
        return dt.strftime(FORMATO_FECHA_VE)

    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        dt = a_vet(dt)

    return dt.strftime(FORMATO_FECHA_VE if solo_fecha else FORMATO_DATETIME_VE)


def inicio_dia_vet(fecha=None) -> datetime:
    """
    Retorna el inicio del día (00:00:00 VET) para una fecha dada.

    Args:
        fecha: date o datetime. Si None, usa hoy en VET.

    Returns:
        datetime con tz=VET al inicio del día.
    """
    from datetime import date

    if fecha is None:
        hoy = ahora_vet().date()
    elif isinstance(fecha, datetime):
        hoy = a_vet(fecha).date() if fecha.tzinfo else fecha.date()
    else:
        hoy = fecha

    return datetime(hoy.year, hoy.month, hoy.day, 0, 0, 0, tzinfo=VET)


def fin_dia_vet(fecha=None) -> datetime:
    """Retorna el fin del día (23:59:59 VET) para una fecha dada."""
    inicio = inicio_dia_vet(fecha)
    return inicio.replace(hour=23, minute=59, second=59, microsecond=999999)
