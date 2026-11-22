"""Servicios del motor trimonetario y multi-tasa extensible (Plan 09 — Ola 1A).

Responsabilidades:
- ``obtener_moneda_referencia_empresa``: resuelve la 3.ª moneda funcional activada
  por empresa (ej. ``USDT``), o ``None`` si está desactivada.
- ``obtener_tasa_por_tipo``: resuelve tasas entre dos monedas permitiendo múltiples
  tipos de tasa por par (``TipoTasaCambio`` extensible + legacy ``tipo_tasa``),
  búsqueda inversa automática y restricción estricta a tasa oficial/fiscal (BCV).
- ``calcular_equivalencias_trimonetarias``: convierte un monto en ``Decimal`` exacto
  simultáneamente a Moneda Base (ej. ``USD``), Moneda País/Fiscal (ej. ``VES`` con
  tasa oficial fiscal obligatoria) y Moneda de Referencia (si está activa).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db.models import Q
from django.utils import timezone

from .cache import _PRIORIDAD_IDX, TIPO_TASA_PRIORIDAD, normalizar_empresa_uuid, obtener_moneda_por_iso
from .models import Moneda, MonedaEmpresaActiva, TasaCambio
from .services import TasaCambioError

_CUATRO_DECIMALES = Decimal("0.0001")
_OCHO_DECIMALES = Decimal("0.00000001")
_UNO = Decimal("1")
_CERO = Decimal("0")


def _resolver_moneda(moneda: Moneda | str, *, empresa_id: Any) -> Moneda:
    """Resuelve una instancia ``Moneda`` a partir de objeto o código ISO."""
    if isinstance(moneda, Moneda):
        return moneda
    if isinstance(moneda, str):
        codigo = moneda.strip().upper()
        if not codigo:
            raise TasaCambioError("Debe indicar una moneda válida.")
        resuelta = obtener_moneda_por_iso(codigo, empresa_id=empresa_id)
        if resuelta is None:
            raise TasaCambioError(f"Moneda '{codigo}' no encontrada.")
        return resuelta
    raise TasaCambioError("Moneda inválida.")


def obtener_moneda_referencia_empresa(empresa: Any) -> Moneda | None:
    """Devuelve la moneda de referencia adicional activa para ``empresa``, o ``None``."""
    empresa_id = normalizar_empresa_uuid(empresa)
    if empresa_id is None:
        return None
    activa = (
        MonedaEmpresaActiva.objects.filter(
            empresa_id=empresa_id,
            activa=True,
            es_moneda_referencia=True,
        )
        .select_related("moneda")
        .first()
    )
    return activa.moneda if activa is not None else None


def _orden_candidata_tasa(tasa: TasaCambio) -> tuple[int, int, float]:
    """Orden de prioridad para seleccionar la mejor tasa candidata dentro de una fecha."""
    es_global = 1 if tasa.id_empresa_id is None else 0
    if tasa.id_tipo_tasa_id and tasa.id_tipo_tasa is not None:
        prioridad = int(tasa.id_tipo_tasa.prioridad)
    else:
        prioridad = _PRIORIDAD_IDX.get(str(tasa.tipo_tasa), len(TIPO_TASA_PRIORIDAD)) + 10
    ts = tasa.fecha_creacion.timestamp() if tasa.fecha_creacion else 0.0
    return (es_global, prioridad, -ts)


def _aplicar_filtros_tipo(
    qs: Any,
    *,
    codigo_upper: str | None,
    solo_oficial_fiscal: bool,
) -> Any:
    if solo_oficial_fiscal:
        qs = qs.filter(Q(id_tipo_tasa__es_oficial_fiscal=True) | Q(tipo_tasa="OFICIAL_BCV"))
    if codigo_upper:
        qs = qs.filter(Q(id_tipo_tasa__codigo=codigo_upper) | Q(tipo_tasa=codigo_upper))
    return qs


def _buscar_tasa_direccional(
    moneda_origen: Moneda,
    moneda_destino: Moneda,
    *,
    empresa_id: Any,
    fecha: date,
    codigo_upper: str | None,
    solo_oficial_fiscal: bool,
) -> TasaCambio | None:
    """Busca primero en ``fecha`` exacta y luego en los últimos 30 días."""
    scope_empresa = Q(id_empresa__isnull=True)
    if empresa_id is not None:
        scope_empresa = scope_empresa | Q(id_empresa_id=empresa_id)

    base_qs = TasaCambio.objects.filter(
        scope_empresa,
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
    ).select_related("id_tipo_tasa", "id_moneda_origen", "id_moneda_destino")
    base_qs = _aplicar_filtros_tipo(base_qs, codigo_upper=codigo_upper, solo_oficial_fiscal=solo_oficial_fiscal)

    exactas = list(base_qs.filter(fecha_tasa=fecha))
    if exactas:
        exactas.sort(key=_orden_candidata_tasa)
        return exactas[0]

    fecha_limite = fecha - timedelta(days=30)
    recientes = list(
        base_qs.filter(fecha_tasa__gte=fecha_limite, fecha_tasa__lte=fecha).order_by("-fecha_tasa", "-fecha_creacion")
    )
    if not recientes:
        return None
    fecha_max = recientes[0].fecha_tasa
    misma_fecha = [t for t in recientes if t.fecha_tasa == fecha_max]
    misma_fecha.sort(key=_orden_candidata_tasa)
    return misma_fecha[0]


def _construir_tasa_inversa(
    tasa_inversa: TasaCambio,
    *,
    moneda_origen: Moneda,
    moneda_destino: Moneda,
) -> TasaCambio:
    """Construye una ``TasaCambio`` en memoria invirtiendo ``destino -> origen``."""
    if tasa_inversa.valor_tasa is None or tasa_inversa.valor_tasa <= _CERO:
        raise TasaCambioError(
            f"La tasa inversa registrada entre {moneda_destino.codigo_iso} y "
            f"{moneda_origen.codigo_iso} debe ser mayor que cero."
        )
    valor_invertido = (_UNO / tasa_inversa.valor_tasa).quantize(_OCHO_DECIMALES, rounding=ROUND_HALF_UP)
    instancia = TasaCambio(
        id_tasa_cambio=tasa_inversa.id_tasa_cambio,
        id_empresa_id=tasa_inversa.id_empresa_id,
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
        id_tipo_tasa=tasa_inversa.id_tipo_tasa,
        tipo_tasa=tasa_inversa.tipo_tasa,
        valor_tasa=valor_invertido,
        fecha_tasa=tasa_inversa.fecha_tasa,
        hora_tasa=tasa_inversa.hora_tasa,
        fecha_creacion=tasa_inversa.fecha_creacion,
    )
    instancia._es_inversa = True  # type: ignore[attr-defined]
    return instancia


def obtener_tasa_por_tipo(
    moneda_origen: Moneda | str,
    moneda_destino: Moneda | str,
    *,
    empresa: Any = None,
    fecha: date | None = None,
    codigo_tipo_tasa: str | None = None,
    solo_oficial_fiscal: bool = False,
) -> TasaCambio:
    """Resuelve la tasa vigente entre dos monedas filtrando por tipo o carácter fiscal.

    Si no existe el par directo ``origen -> destino``, intenta resolver el par
    inverso ``destino -> origen`` calculando ``1 / valor_tasa``.
    """
    empresa_id = normalizar_empresa_uuid(empresa)
    origen = _resolver_moneda(moneda_origen, empresa_id=empresa_id)
    destino = _resolver_moneda(moneda_destino, empresa_id=empresa_id)

    if fecha is None:
        fecha = timezone.localdate()

    if origen.pk == destino.pk:
        identidad = TasaCambio(
            id_moneda_origen=origen,
            id_moneda_destino=destino,
            tipo_tasa="FIJA",
            valor_tasa=Decimal("1.00000000"),
            fecha_tasa=fecha,
        )
        identidad._es_inversa = False  # type: ignore[attr-defined]
        return identidad

    codigo_upper = codigo_tipo_tasa.strip().upper() if codigo_tipo_tasa and codigo_tipo_tasa.strip() else None

    directa = _buscar_tasa_direccional(
        origen,
        destino,
        empresa_id=empresa_id,
        fecha=fecha,
        codigo_upper=codigo_upper,
        solo_oficial_fiscal=solo_oficial_fiscal,
    )
    if directa is not None:
        directa._es_inversa = False  # type: ignore[attr-defined]
        return directa

    inversa = _buscar_tasa_direccional(
        destino,
        origen,
        empresa_id=empresa_id,
        fecha=fecha,
        codigo_upper=codigo_upper,
        solo_oficial_fiscal=solo_oficial_fiscal,
    )
    if inversa is not None:
        return _construir_tasa_inversa(inversa, moneda_origen=origen, moneda_destino=destino)

    detalle_tipo = f" (tipo={codigo_upper})" if codigo_upper else ""
    detalle_fiscal = " oficial/fiscal" if solo_oficial_fiscal else ""
    raise TasaCambioError(
        f"No hay tasa de cambio{detalle_fiscal}{detalle_tipo} disponible entre "
        f"{origen.codigo_iso} y {destino.codigo_iso} para {fecha} (últimos 30 días)."
    )


def _serializar_meta_tasa(tasa: TasaCambio, *, solo_oficial_fiscal: bool = False) -> dict[str, Any]:
    tipo_codigo = tasa.id_tipo_tasa.codigo if tasa.id_tipo_tasa_id and tasa.id_tipo_tasa else tasa.tipo_tasa
    es_oficial = bool(
        solo_oficial_fiscal
        or (tasa.id_tipo_tasa_id and tasa.id_tipo_tasa and tasa.id_tipo_tasa.es_oficial_fiscal)
        or tasa.tipo_tasa == "OFICIAL_BCV"
    )
    return {
        "valor_tasa": tasa.valor_tasa.quantize(_OCHO_DECIMALES, rounding=ROUND_HALF_UP),
        "tipo_tasa": tipo_codigo,
        "fecha_tasa": tasa.fecha_tasa,
        "es_inversa": bool(getattr(tasa, "_es_inversa", False)),
        "es_oficial_fiscal": es_oficial,
    }


def _convertir_con_tasa(
    monto: Decimal,
    moneda_origen: Moneda,
    moneda_destino: Moneda | None,
    *,
    empresa: Any,
    fecha: date,
    codigo_tipo_tasa: str | None = None,
    solo_oficial_fiscal: bool = False,
) -> tuple[Decimal | None, dict[str, Any] | None]:
    if moneda_destino is None:
        return None, None
    tasa = obtener_tasa_por_tipo(
        moneda_origen,
        moneda_destino,
        empresa=empresa,
        fecha=fecha,
        codigo_tipo_tasa=codigo_tipo_tasa,
        solo_oficial_fiscal=solo_oficial_fiscal,
    )
    monto_convertido = (monto * tasa.valor_tasa).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    return monto_convertido, _serializar_meta_tasa(tasa, solo_oficial_fiscal=solo_oficial_fiscal)


def calcular_equivalencias_trimonetarias(
    monto: Decimal | str | int,
    moneda_origen: Moneda | str,
    *,
    empresa: Any,
    fecha: date | None = None,
    codigo_tipo_tasa_base: str | None = None,
    codigo_tipo_tasa_referencia: str | None = None,
) -> dict[str, Any]:
    """Convierte ``monto`` simultáneamente a Base, País/Fiscal (BCV) y Referencia.

    - Moneda Base (ej. USD): usa ``codigo_tipo_tasa_base`` si se indica, o la prioridad vigente.
    - Moneda País/Fiscal (ej. VES): exige ``solo_oficial_fiscal=True`` (tasa oficial BCV).
    - Moneda Referencia (ej. USDT): solo se calcula si la empresa tiene activa una
      ``MonedaEmpresaActiva(es_moneda_referencia=True, activa=True)``.
    """
    if empresa is None:
        raise TasaCambioError("Debe especificar una empresa válida para el cálculo trimonetario.")
    try:
        monto_dec = Decimal(str(monto))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("El monto debe ser un número decimal válido.") from exc
    if monto_dec < _CERO:
        raise ValueError("El monto a convertir no puede ser negativo.")
    monto_dec = monto_dec.quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)

    if fecha is None:
        fecha = timezone.localdate()

    empresa_id = normalizar_empresa_uuid(empresa)
    origen = _resolver_moneda(moneda_origen, empresa_id=empresa_id)
    moneda_base = getattr(empresa, "id_moneda_base", None)
    moneda_pais = getattr(empresa, "id_moneda_pais", None)
    moneda_referencia = obtener_moneda_referencia_empresa(empresa)

    monto_base, tasa_base = _convertir_con_tasa(
        monto_dec,
        origen,
        moneda_base,
        empresa=empresa,
        fecha=fecha,
        codigo_tipo_tasa=codigo_tipo_tasa_base,
        solo_oficial_fiscal=False,
    )
    monto_pais, tasa_pais = _convertir_con_tasa(
        monto_dec,
        origen,
        moneda_pais,
        empresa=empresa,
        fecha=fecha,
        codigo_tipo_tasa=None,
        solo_oficial_fiscal=True,
    )
    monto_ref, tasa_ref = _convertir_con_tasa(
        monto_dec,
        origen,
        moneda_referencia,
        empresa=empresa,
        fecha=fecha,
        codigo_tipo_tasa=codigo_tipo_tasa_referencia,
        solo_oficial_fiscal=False,
    )

    return {
        "fecha": fecha,
        "moneda_origen_id": str(origen.pk),
        "moneda_origen_iso": origen.codigo_iso,
        "moneda_origen_simbolo": origen.simbolo,
        "monto_origen": monto_dec,
        "moneda_base_id": str(moneda_base.pk) if moneda_base else None,
        "moneda_base_iso": moneda_base.codigo_iso if moneda_base else None,
        "moneda_base_simbolo": moneda_base.simbolo if moneda_base else None,
        "monto_base": monto_base,
        "tasa_base": tasa_base,
        "moneda_pais_id": str(moneda_pais.pk) if moneda_pais else None,
        "moneda_pais_iso": moneda_pais.codigo_iso if moneda_pais else None,
        "moneda_pais_simbolo": moneda_pais.simbolo if moneda_pais else None,
        "monto_pais_fiscal": monto_pais,
        "tasa_pais_fiscal": tasa_pais,
        "moneda_referencia_activa": moneda_referencia is not None,
        "moneda_referencia_id": str(moneda_referencia.pk) if moneda_referencia else None,
        "moneda_referencia_iso": moneda_referencia.codigo_iso if moneda_referencia else None,
        "moneda_referencia_simbolo": moneda_referencia.simbolo if moneda_referencia else None,
        "monto_referencia": monto_ref,
        "tasa_referencia": tasa_ref,
    }
