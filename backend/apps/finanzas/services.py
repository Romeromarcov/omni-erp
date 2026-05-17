"""
Servicios de negocio para Finanzas.

obtener_tasa_cambio()  — busca la mejor tasa disponible entre dos monedas.
convertir_monto()      — convierte un monto usando la tasa vigente.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone


class TasaCambioError(Exception):
    pass


# Priority order for rate lookup (lowest index = highest priority)
_TIPO_TASA_PRIORIDAD = ["ESPECIAL_USUARIO", "FIJA", "PROMEDIO_MERCADO", "OFICIAL_BCV"]


def obtener_tasa_cambio(moneda_origen, moneda_destino, empresa=None, fecha=None):
    """
    Busca la tasa de cambio más adecuada entre dos monedas para una fecha.

    Prioridad de búsqueda:
    1. Tasa específica de la empresa (ESPECIAL_USUARIO > FIJA > PROMEDIO_MERCADO) para la fecha exacta.
    2. Tasa global OFICIAL_BCV (id_empresa=None) para la fecha exacta.
    3. Tasa más reciente disponible (empresa-específica o global) dentro de los últimos 30 días.

    Si moneda_origen == moneda_destino devuelve tasa 1.0.

    Args:
        moneda_origen:  Instancia Moneda o código ISO (str).
        moneda_destino: Instancia Moneda o código ISO (str).
        empresa:        Instancia Empresa o UUID; puede ser None para buscar solo tasas globales.
        fecha:          date — fecha de referencia; default hoy (timezone.now().date()).

    Returns:
        TasaCambio — instancia con la mejor tasa disponible.

    Raises:
        TasaCambioError si no se encuentra ninguna tasa.
    """
    from .models import Moneda, TasaCambio

    # Resolver monedas por ISO si se pasan como strings
    if isinstance(moneda_origen, str):
        try:
            moneda_origen = Moneda.objects.get(codigo_iso=moneda_origen)
        except Moneda.DoesNotExist:
            raise TasaCambioError(f"Moneda '{moneda_origen}' no encontrada.")
    if isinstance(moneda_destino, str):
        try:
            moneda_destino = Moneda.objects.get(codigo_iso=moneda_destino)
        except Moneda.DoesNotExist:
            raise TasaCambioError(f"Moneda '{moneda_destino}' no encontrada.")

    # Misma moneda — tasa identidad (usamos un stub no persistente)
    if moneda_origen.pk == moneda_destino.pk:
        tasa = TasaCambio(
            id_moneda_origen=moneda_origen,
            id_moneda_destino=moneda_destino,
            valor_tasa=Decimal("1.00000000"),
            fecha_tasa=timezone.now().date(),
            tipo_tasa="FIJA",
        )
        return tasa

    if fecha is None:
        fecha = timezone.now().date()

    base_qs = TasaCambio.objects.filter(
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
        fecha_tasa=fecha,
    )

    # 1. Tasa empresa-específica (fecha exacta)
    if empresa is not None:
        empresa_qs = base_qs.filter(id_empresa=empresa)
        for tipo in _TIPO_TASA_PRIORIDAD:
            tasa = empresa_qs.filter(tipo_tasa=tipo).order_by("-fecha_creacion").first()
            if tasa:
                return tasa

    # 2. Tasa global OFICIAL_BCV (fecha exacta)
    tasa = base_qs.filter(id_empresa=None, tipo_tasa="OFICIAL_BCV").order_by("-fecha_creacion").first()
    if tasa:
        return tasa

    # 3. Tasa más reciente disponible (últimos 30 días)
    from datetime import timedelta

    fecha_limite = fecha - timedelta(days=30)
    recientes_qs = TasaCambio.objects.filter(
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
        fecha_tasa__gte=fecha_limite,
        fecha_tasa__lte=fecha,
    ).order_by("-fecha_tasa", "-fecha_creacion")

    if empresa is not None:
        tasa = recientes_qs.filter(id_empresa=empresa).first()
        if tasa:
            return tasa

    tasa = recientes_qs.filter(id_empresa=None).first()
    if tasa:
        return tasa

    raise TasaCambioError(
        f"No hay tasa de cambio disponible entre {moneda_origen.codigo_iso} "
        f"y {moneda_destino.codigo_iso} para {fecha} (últimos 30 días)."
    )


def convertir_monto(monto: Decimal, moneda_origen, moneda_destino, empresa=None, fecha=None) -> Decimal:
    """
    Convierte un monto de moneda_origen a moneda_destino.

    Args:
        monto:          Monto a convertir (Decimal o numérico).
        moneda_origen:  Instancia Moneda o código ISO.
        moneda_destino: Instancia Moneda o código ISO.
        empresa:        Instancia Empresa o UUID; None para tasas globales.
        fecha:          date; default hoy.

    Returns:
        Decimal — monto convertido, redondeado a 4 decimales.

    Raises:
        TasaCambioError si no hay tasa disponible.
        ValueError si el monto es negativo.
    """
    monto = Decimal(str(monto))
    if monto < 0:
        raise ValueError("El monto a convertir no puede ser negativo.")

    tasa = obtener_tasa_cambio(moneda_origen, moneda_destino, empresa=empresa, fecha=fecha)
    resultado = monto * tasa.valor_tasa
    return resultado.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
