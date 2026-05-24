"""
M10-T6: Calendario de feriados venezolanos.

Incluye feriados nacionales fijos y móviles (Semana Santa calculada).
Fuente: Ley Orgánica del Trabajo, Artículo 184 y legislación vigente.

Uso:
    from apps.vzla_localizacion.calendario import es_feriado, feriados_del_año, dias_habiles
    print(es_feriado(date(2026, 1, 1)))   # True (Año Nuevo)
    print(dias_habiles(date(2026, 1, 1), date(2026, 1, 31)))
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional


# ── Feriados fijos nacionales ─────────────────────────────────────────────────

_FERIADOS_FIJOS: list[tuple[int, int, str]] = [
    (1,  1,  "Año Nuevo"),
    (1,  15, "Día del Maestro"),          # Variable pero comúnmente el 15/1
    (3,  19, "San José"),                 # 19 de marzo
    (4,  19, "19 de Abril — Proclamación de Independencia"),
    (5,  1,  "Día del Trabajador"),
    (6,  24, "Batalla de Carabobo"),
    (7,  5,  "Día de la Independencia"),
    (7,  24, "Natalicio de Simón Bolívar"),
    (10, 12, "Día de la Resistencia Indígena"),
    (11, 1,  "Todos los Santos"),
    (12, 8,  "Inmaculada Concepción"),
    (12, 17, "Muerte de Simón Bolívar"),
    (12, 24, "Nochebuena"),
    (12, 25, "Navidad"),
    (12, 31, "Nochevieja"),
]


def _calcular_semana_santa(año: int) -> set[date]:
    """
    Calcula las fechas de Semana Santa para un año dado (algoritmo de Meeus/Jones/Butcher).
    Retorna: Jueves Santo, Viernes Santo, Lunes de Pascua.
    """
    a = año % 19
    b, c = divmod(año, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1

    domingo_pascua = date(año, mes, dia)
    viernes_santo = domingo_pascua - timedelta(days=2)
    jueves_santo = domingo_pascua - timedelta(days=3)
    miercoles_ceniza = domingo_pascua - timedelta(days=46)
    lunes_pascua = domingo_pascua + timedelta(days=1)

    return {jueves_santo, viernes_santo, lunes_pascua}


def feriados_del_año(año: int) -> dict[date, str]:
    """
    Retorna todos los feriados nacionales venezolanos de un año.

    Args:
        año: Año a calcular.

    Returns:
        Dict {date: descripcion} con todos los feriados.
    """
    resultado: dict[date, str] = {}

    # Fijos
    for mes, dia, nombre in _FERIADOS_FIJOS:
        try:
            resultado[date(año, mes, dia)] = nombre
        except ValueError:
            pass  # fecha inválida para ese año (ej. 29/2 en no bisiesto)

    # Semana Santa (móvil)
    for fecha_ss in _calcular_semana_santa(año):
        resultado[fecha_ss] = "Semana Santa"

    # Carnaval (lunes y martes antes del Miércoles de Ceniza)
    a = año % 19
    b, c = divmod(año, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes_p = (h + l - 7 * m + 114) // 31
    dia_p = ((h + l - 7 * m + 114) % 31) + 1
    domingo_pascua = date(año, mes_p, dia_p)
    miercoles_ceniza = domingo_pascua - timedelta(days=46)
    resultado[miercoles_ceniza - timedelta(days=1)] = "Martes de Carnaval"
    resultado[miercoles_ceniza - timedelta(days=2)] = "Lunes de Carnaval"

    return resultado


def es_feriado(fecha: date, año: Optional[int] = None) -> bool:
    """
    Verifica si una fecha es feriado nacional venezolano.

    Args:
        fecha: Fecha a verificar.
        año:   Si se provee, usa el dict precalculado de ese año (optimización).

    Returns:
        True si la fecha es feriado.
    """
    feriados = feriados_del_año(fecha.year)
    return fecha in feriados


def es_dia_habil(fecha: date) -> bool:
    """
    Verifica si una fecha es día hábil (no feriado y no fin de semana).

    Args:
        fecha: Fecha a verificar.

    Returns:
        True si es día hábil.
    """
    if fecha.weekday() >= 5:  # sábado=5, domingo=6
        return False
    return not es_feriado(fecha)


def dias_habiles(fecha_inicio: date, fecha_fin: date) -> int:
    """
    Cuenta los días hábiles entre dos fechas (inclusivas).

    Args:
        fecha_inicio: Fecha de inicio (inclusive).
        fecha_fin:    Fecha de fin (inclusive).

    Returns:
        Número de días hábiles.
    """
    if fecha_inicio > fecha_fin:
        return 0

    # Precalcular feriados por año
    años = set(range(fecha_inicio.year, fecha_fin.year + 1))
    feriados_set: set[date] = set()
    for año in años:
        feriados_set.update(feriados_del_año(año).keys())

    count = 0
    current = fecha_inicio
    while current <= fecha_fin:
        if current.weekday() < 5 and current not in feriados_set:
            count += 1
        current += timedelta(days=1)
    return count


def siguiente_dia_habil(fecha: date) -> date:
    """
    Retorna el siguiente día hábil a partir de una fecha (sin incluirla).

    Args:
        fecha: Fecha de referencia.

    Returns:
        Siguiente día hábil.
    """
    siguiente = fecha + timedelta(days=1)
    feriados = feriados_del_año(siguiente.year)
    for _ in range(60):  # máximo 60 días de búsqueda
        if siguiente.weekday() < 5 and siguiente not in feriados:
            return siguiente
        siguiente += timedelta(days=1)
        if siguiente.year != fecha.year:
            feriados.update(feriados_del_año(siguiente.year))
    raise RuntimeError("No se encontró día hábil en 60 días")
