"""Motor dinámico de precios por brecha cambiaria, moneda de pago, zona, segmento y volumen (Plan 09 §3.1)."""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

_CUATRO_DECIMALES = Decimal("0.0001")
_CIEN = Decimal("100")
_UNO = Decimal("1")
_CERO = Decimal("0")


def _resolver_precio_base_y_minimo(
    producto, empresa, contacto=None, fecha: date | None = None
) -> tuple[Decimal, Decimal]:
    """Obtiene el precio base (obtener_precio) y el precio_minimo de la lista aplicable."""
    from apps.ventas.models import DetallePrecio, ListaPrecio
    from apps.ventas.services import obtener_precio

    hoy = fecha or timezone.localdate()
    precio_base = Decimal(str(obtener_precio(producto, empresa, contacto=contacto, fecha=hoy)))
    precio_minimo = Decimal("0")

    listas_candidatas = []
    if contacto is not None and getattr(contacto, "lista_precio_id", None):
        listas_candidatas.append(contacto.lista_precio_id)
    lista_ref = ListaPrecio.objects.filter(id_empresa=empresa, es_referencia=True, activo=True).first()
    if lista_ref is not None:
        listas_candidatas.append(lista_ref.pk)

    for lista_id in listas_candidatas:
        dp = (
            DetallePrecio.objects.filter(id_lista_id=lista_id, id_producto=producto, activo=True)
            .filter(models.Q(vigente_desde__isnull=True) | models.Q(vigente_desde__lte=hoy))
            .filter(models.Q(vigente_hasta__isnull=True) | models.Q(vigente_hasta__gte=hoy))
            .first()
        )
        if dp is not None:
            if dp.precio_minimo and dp.precio_minimo > 0:
                precio_minimo = Decimal(str(dp.precio_minimo))
            break

    return precio_base.quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP), precio_minimo.quantize(
        _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
    )


def _regla_coincide(
    regla,
    *,
    producto,
    cantidad: Decimal,
    moneda_pago_upper: str,
    zona_upper: str,
    segmento_upper: str,
) -> bool:
    if regla.producto_id is not None and regla.producto_id != producto.pk:
        return False
    if regla.categoria_id is not None and regla.categoria_id != getattr(producto, "id_categoria_id", None):
        return False
    if cantidad < Decimal(str(regla.cantidad_minima or "0")):
        return False

    cond = (regla.clave_condicion or "").strip().upper()
    if regla.tipo_factor in ("MONEDA_PAGO", "BRECHA_CAMBIARIA"):
        return not cond or cond == moneda_pago_upper
    if regla.tipo_factor == "ZONA":
        return bool(zona_upper) and (not cond or cond == zona_upper)
    if regla.tipo_factor == "SEGMENTO":
        return bool(segmento_upper) and (not cond or cond == segmento_upper)
    # VOLUMEN: ya validamos cantidad >= cantidad_minima
    return True


def _factor_brecha_tasa(
    empresa,
    regla,
    *,
    fecha: date,
    moneda_base_iso: str,
    tipo_tasa_fallback: str | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Calcula multiplicador por brecha entre tasa referencia y BCV oficial."""
    from apps.finanzas.services import TasaCambioError
    from apps.finanzas.services_trimonetario import obtener_tasa_por_tipo

    moneda_pais = getattr(empresa, "id_moneda_pais", None)
    if moneda_pais is None:
        return None, None
    pais_iso = moneda_pais.codigo_iso
    if not pais_iso or pais_iso == moneda_base_iso:
        return None, None

    codigo_ref = (regla.codigo_tipo_tasa_referencia or tipo_tasa_fallback or "").strip().upper() or None
    try:
        tasa_bcv = obtener_tasa_por_tipo(
            moneda_base_iso,
            pais_iso,
            empresa=empresa,
            fecha=fecha,
            solo_oficial_fiscal=True,
        )
        tasa_ref = obtener_tasa_por_tipo(
            moneda_base_iso,
            pais_iso,
            empresa=empresa,
            fecha=fecha,
            codigo_tipo_tasa=codigo_ref,
            solo_oficial_fiscal=False,
        )
    except TasaCambioError:
        return None, None

    val_bcv = Decimal(str(tasa_bcv.valor_tasa))
    val_ref = Decimal(str(tasa_ref.valor_tasa))
    if val_bcv <= _CERO or val_ref <= _CERO:
        return None, None

    brecha_rel = (val_ref / val_bcv) - _UNO
    brecha_pct = (brecha_rel * _CIEN).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    if brecha_rel <= _CERO:
        return _UNO, brecha_pct

    peso = Decimal(str(regla.valor_factor or "100")) / _CIEN
    factor = _UNO + (brecha_rel * peso)
    return factor, brecha_pct


def calcular_precio_dinamico(
    producto,
    empresa,
    *,
    contacto=None,
    cantidad: Decimal | str | int = Decimal("1"),
    moneda_pago: str = "USD",
    zona: str = "",
    segmento: str = "",
    fecha: date | None = None,
    tipo_tasa_referencia: str | None = None,
) -> dict[str, Any]:
    """Calcula precio unitario dinámico componiendo reglas VE y equivalencias trimonetarias."""
    from apps.finanzas.services import TasaCambioError
    from apps.finanzas.services_trimonetario import calcular_equivalencias_trimonetarias
    from apps.ventas.models import ReglaPrecioDinamico
    from apps.ventas.services import VentaError

    cant = Decimal(str(cantidad))
    if cant <= _CERO:
        raise VentaError("La cantidad a cotizar debe ser mayor que cero.")

    hoy = fecha or timezone.localdate()
    precio_base, precio_minimo = _resolver_precio_base_y_minimo(producto, empresa, contacto=contacto, fecha=hoy)

    zona_eff = (zona or getattr(contacto, "estado", "") or getattr(contacto, "municipio", "") or "").strip().upper()
    moneda_pago_upper = (moneda_pago or "USD").strip().upper()
    segmento_upper = (segmento or "").strip().upper()
    moneda_base = getattr(empresa, "id_moneda_base", None)
    moneda_base_iso = moneda_base.codigo_iso if moneda_base is not None else "USD"

    reglas = list(
        ReglaPrecioDinamico.objects.filter(id_empresa=empresa, activo=True)
        .filter(models.Q(vigente_desde__isnull=True) | models.Q(vigente_desde__lte=hoy))
        .filter(models.Q(vigente_hasta__isnull=True) | models.Q(vigente_hasta__gte=hoy))
        .order_by("prioridad", "fecha_creacion")
    )

    precio_actual = precio_base
    brecha_pct_detectada: Decimal | None = None
    reglas_aplicadas: list[dict[str, Any]] = []

    for regla in reglas:
        if not _regla_coincide(
            regla,
            producto=producto,
            cantidad=cant,
            moneda_pago_upper=moneda_pago_upper,
            zona_upper=zona_eff,
            segmento_upper=segmento_upper,
        ):
            continue

        precio_antes = precio_actual
        if regla.modo_calculo == "MULTIPLICADOR":
            factor = Decimal(str(regla.valor_factor))
            if factor <= _CERO:
                continue
            precio_actual = precio_actual * factor
        elif regla.modo_calculo == "PORCENTAJE":
            pct = Decimal(str(regla.valor_factor))
            precio_actual = precio_actual * (_UNO + pct / _CIEN)
        elif regla.modo_calculo == "BRECHA_TASA":
            factor_brecha, brecha_pct = _factor_brecha_tasa(
                empresa,
                regla,
                fecha=hoy,
                moneda_base_iso=moneda_base_iso,
                tipo_tasa_fallback=tipo_tasa_referencia,
            )
            if factor_brecha is None:
                continue
            brecha_pct_detectada = brecha_pct
            precio_actual = precio_actual * factor_brecha
        else:
            continue

        reglas_aplicadas.append(
            {
                "id_regla": str(regla.id_regla),
                "codigo": regla.codigo,
                "nombre": regla.nombre,
                "tipo_factor": regla.tipo_factor,
                "modo_calculo": regla.modo_calculo,
                "valor_factor": str(regla.valor_factor),
                "precio_antes": str(precio_antes.quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)),
                "precio_despues": str(precio_actual.quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)),
            }
        )
        if not regla.acumulable:
            break

    precio_final = max(precio_actual, _CERO).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    precio_minimo_aplicado = False
    if precio_minimo > _CERO and precio_final < precio_minimo:
        precio_final = precio_minimo
        precio_minimo_aplicado = True

    descuento_recargo_pct = _CERO
    if precio_base > _CERO:
        descuento_recargo_pct = (((precio_final - precio_base) / precio_base) * _CIEN).quantize(
            _CUATRO_DECIMALES, rounding=ROUND_HALF_UP
        )

    total_linea = (precio_final * cant).quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)

    equivalencias = None
    if moneda_base is not None:
        try:
            equivalencias = calcular_equivalencias_trimonetarias(
                precio_final,
                moneda_base,
                empresa=empresa,
                fecha=hoy,
            )
        except TasaCambioError:
            equivalencias = None

    return {
        "producto_id": str(producto.pk),
        "cantidad": cant,
        "moneda_pago": moneda_pago_upper,
        "zona": zona_eff,
        "segmento": segmento_upper,
        "precio_base": precio_base,
        "precio_final": precio_final,
        "total_linea": total_linea,
        "precio_minimo": precio_minimo,
        "precio_minimo_aplicado": precio_minimo_aplicado,
        "descuento_recargo_pct": descuento_recargo_pct,
        "brecha_cambiaria_pct": brecha_pct_detectada,
        "reglas_aplicadas": reglas_aplicadas,
        "equivalencias": equivalencias,
    }
