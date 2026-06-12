"""
Libro maestro de caja — Capa B §6.8 (plan §6.7, "maestro de operaciones").

Vista consolidada de los movimientos de TODAS las cajas de la empresa (físicas
y virtuales) en un rango de fechas: saldo inicial, entradas, salidas y saldo
final por caja, y totales agrupados por moneda — NUNCA se suman montos de
monedas distintas (R-CODE-4).

Decisiones de diseño:
- La fuente de verdad es el propio log de ``MovimientoCajaBanco`` (el libro es
  auto-consistente y auditable): ``saldo_inicial`` = Σ entradas − Σ salidas de
  los movimientos ANTERIORES a ``fecha_desde`` (base 0). Es matemáticamente
  equivalente al corte persistente de ``realizar_cierre_caja`` porque cada
  cierre materializa su descuadre como movimiento de AJUSTE; no se usa el
  ``saldo_actual`` vivo (que incluye movimientos posteriores al rango).
- Tipos de entrada/salida por tipo de caja: espejo de ``realizar_cierre_caja``
  (las virtuales incluyen transferencias internas; las físicas no las usan).
  Los movimientos ``CIERRE`` son cortes con monto 0: no afectan sumas.
- Moneda por fila: las cajas virtuales son mono-moneda (``caja.moneda``); las
  físicas pueden mover varias monedas, así que se emite UNA fila por
  (caja física, moneda de movimiento). Movimientos físicos sin moneda
  (ajustes legacy) se agrupan bajo ``moneda=None``.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

#: Tipos que suman (entradas) y restan (salidas), espejo de realizar_cierre_caja.
TIPOS_ENTRADA_VIRTUAL = ("INGRESO", "AJUSTE_POSITIVO", "TRANSFERENCIA_ENTRADA")
TIPOS_SALIDA_VIRTUAL = ("EGRESO", "AJUSTE_NEGATIVO", "TRANSFERENCIA_SALIDA")
TIPOS_ENTRADA_FISICA = ("INGRESO", "AJUSTE_POSITIVO")
TIPOS_SALIDA_FISICA = ("EGRESO", "AJUSTE_NEGATIVO")

_CERO = Decimal("0.00")


def _sumas(movimientos, tipos_entrada, tipos_salida, desde, hasta):
    """
    Calcula (saldo_inicial, entradas, salidas, n_movimientos) de un queryset de
    movimientos: lo anterior a ``desde`` forma el saldo inicial; lo que cae en
    [desde, hasta] (por ``fecha_movimiento``) son las entradas/salidas del rango.
    """
    previos = movimientos.filter(fecha_movimiento__lt=desde)
    ventana = movimientos.filter(fecha_movimiento__gte=desde, fecha_movimiento__lte=hasta)

    def _suma(qs, tipos):
        return qs.filter(tipo_movimiento__in=tipos).aggregate(s=Sum("monto"))["s"] or _CERO

    saldo_inicial = _suma(previos, tipos_entrada) - _suma(previos, tipos_salida)
    entradas = _suma(ventana, tipos_entrada)
    salidas = _suma(ventana, tipos_salida)
    return saldo_inicial, entradas, salidas, ventana.count()


def _fila(*, caja_id, tipo, nombre, tipo_caja, moneda, saldo_inicial, entradas, salidas, movimientos):
    return {
        "id_caja": str(caja_id),
        "tipo": tipo,  # "VIRTUAL" | "FISICA"
        "nombre": nombre,
        "tipo_caja": tipo_caja,
        "moneda": moneda.codigo_iso if moneda is not None else None,
        "saldo_inicial": saldo_inicial,
        "entradas": entradas,
        "salidas": salidas,
        "saldo_final": saldo_inicial + entradas - salidas,
        "movimientos": movimientos,
    }


def generar_libro_maestro_caja(
    empresa,
    fecha_desde,
    fecha_hasta,
    *,
    incluir_inactivas: bool = False,
    moneda_codigo: str | None = None,
    tipo: str | None = None,
):
    """
    Genera el libro maestro de caja de una empresa para [fecha_desde, fecha_hasta].

    Args:
        empresa:           instancia ``core.Empresa`` (el caller valida acceso, R-CODE-1).
        fecha_desde:       date inicio del rango (inclusive).
        fecha_hasta:       date fin del rango (inclusive).
        incluir_inactivas: incluir cajas desactivadas (default False).
        moneda_codigo:     filtrar filas por código ISO de moneda (ej. "USD").
        tipo:              filtrar por tipo de caja: "VIRTUAL" | "FISICA".

    Returns:
        dict con ``cajas`` (una fila por caja virtual y por (caja física,
        moneda)) y ``totales_por_moneda`` (consolidado SIN mezclar monedas).
        Montos en Decimal — el serializador de la vista los emite como str.

    Raises:
        ValueError: si fecha_desde > fecha_hasta o el tipo es desconocido.
    """
    from .models import Caja, CajaFisica, Moneda

    if fecha_desde > fecha_hasta:
        raise ValueError("'fecha_desde' no puede ser posterior a 'fecha_hasta'.")
    if tipo is not None and tipo not in ("VIRTUAL", "FISICA"):
        raise ValueError("Tipo de caja inválido: use 'VIRTUAL' o 'FISICA'.")

    filas: list[dict] = []

    # ── Cajas virtuales (mono-moneda: caja.moneda) ────────────────────────────
    if tipo in (None, "VIRTUAL"):
        cajas_virtuales = Caja.objects.filter(empresa=empresa).select_related("moneda")
        if not incluir_inactivas:
            cajas_virtuales = cajas_virtuales.filter(activa=True)
        if moneda_codigo:
            cajas_virtuales = cajas_virtuales.filter(moneda__codigo_iso=moneda_codigo)
        for caja in cajas_virtuales.order_by("nombre"):
            saldo_inicial, entradas, salidas, n = _sumas(
                caja.movimientos.all(),
                TIPOS_ENTRADA_VIRTUAL,
                TIPOS_SALIDA_VIRTUAL,
                fecha_desde,
                fecha_hasta,
            )
            filas.append(
                _fila(
                    caja_id=caja.id_caja,
                    tipo="VIRTUAL",
                    nombre=caja.nombre,
                    tipo_caja=caja.tipo_caja,
                    moneda=caja.moneda,
                    saldo_inicial=saldo_inicial,
                    entradas=entradas,
                    salidas=salidas,
                    movimientos=n,
                )
            )

    # ── Cajas físicas (multi-moneda: una fila por moneda con movimientos) ────
    if tipo in (None, "FISICA"):
        cajas_fisicas = CajaFisica.objects.filter(empresa=empresa)
        if not incluir_inactivas:
            cajas_fisicas = cajas_fisicas.filter(activa=True)
        for caja_fis in cajas_fisicas.order_by("nombre"):
            # Los CIERRE (cortes monto 0, sin moneda) no definen grupos de moneda.
            relevantes = caja_fis.movimientos.filter(fecha_movimiento__lte=fecha_hasta).exclude(
                tipo_movimiento="CIERRE"
            )
            moneda_ids = set(relevantes.values_list("id_moneda", flat=True).distinct())
            monedas = {m.pk: m for m in Moneda.objects.filter(pk__in={i for i in moneda_ids if i})}
            grupos = sorted(
                moneda_ids,
                key=lambda mid: monedas[mid].codigo_iso if mid in monedas else "",
            )
            if not grupos:
                grupos = [None]  # caja sin movimientos: visible con ceros
            for moneda_id in grupos:
                moneda = monedas.get(moneda_id) if moneda_id is not None else None
                if moneda_codigo and (moneda is None or moneda.codigo_iso != moneda_codigo):
                    continue
                saldo_inicial, entradas, salidas, n = _sumas(
                    caja_fis.movimientos.filter(id_moneda=moneda_id),
                    TIPOS_ENTRADA_FISICA,
                    TIPOS_SALIDA_FISICA,
                    fecha_desde,
                    fecha_hasta,
                )
                filas.append(
                    _fila(
                        caja_id=caja_fis.id_caja_fisica,
                        tipo="FISICA",
                        nombre=caja_fis.nombre,
                        tipo_caja=caja_fis.tipo_caja,
                        moneda=moneda,
                        saldo_inicial=saldo_inicial,
                        entradas=entradas,
                        salidas=salidas,
                        movimientos=n,
                    )
                )

    # ── Totales por moneda (NUNCA se suman monedas distintas) ────────────────
    totales: dict[str | None, dict] = {}
    for fila in filas:
        clave = fila["moneda"]
        if clave not in totales:
            totales[clave] = {
                "moneda": clave,
                "saldo_inicial": _CERO,
                "entradas": _CERO,
                "salidas": _CERO,
                "saldo_final": _CERO,
                "cajas": 0,
            }
        t = totales[clave]
        t["saldo_inicial"] += fila["saldo_inicial"]
        t["entradas"] += fila["entradas"]
        t["salidas"] += fila["salidas"]
        t["saldo_final"] += fila["saldo_final"]
        t["cajas"] += 1

    totales_orden = sorted(totales.values(), key=lambda t: (t["moneda"] is None, t["moneda"] or ""))

    return {
        "empresa": str(empresa.pk),
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "cajas": filas,
        "totales_por_moneda": totales_orden,
    }
