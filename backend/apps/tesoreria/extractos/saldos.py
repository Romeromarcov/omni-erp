"""Consolidación multi-tenant de saldos de extractos bancarios y continuidad entre cortes.

Los saldos se consolidan a partir de los cortes (``ExtractoBancarioArchivo``), no
sumando movimientos sueltos: el saldo fehaciente es el reportado por el banco tras
validar la cadena fila a fila.

Además verifica la continuidad entre cortes consecutivos no solapados de una misma
cuenta bancaria: si ``saldo_inicial`` del corte siguiente difiere de ``saldo_final``
del corte anterior, alerta explícitamente sobre el hueco entre fechas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from .modelos_canonicos import CERO, TOL

_DOS_DECIMALES = Decimal("0.01")


def _q2(valor: Decimal) -> Decimal:
    return valor.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CorteExtracto:
    archivo_id: str
    cuenta_id: str
    nombre_banco: str
    numero_cuenta: str
    moneda: str
    nombre_archivo: str
    fecha_desde: date | None
    fecha_hasta: date | None
    saldo_inicial: Decimal | None
    saldo_final: Decimal | None
    cuadra: bool
    cargado_en: datetime


@dataclass
class SaldoCuentaExtracto:
    cuenta_id: str
    nombre_banco: str
    numero_cuenta: str
    moneda: str
    fecha_corte: date | None
    saldo: Decimal | None
    tasa_usd_ves: Decimal | None
    saldo_usd: Decimal | None
    saldo_ves: Decimal | None
    n_cortes: int
    cortes_sin_cuadrar: int
    alertas: list[str] = field(default_factory=list)


@dataclass
class ConsolidadoExtractos:
    cuentas: list[SaldoCuentaExtracto]
    total_usd: Decimal
    total_ves: Decimal
    cuentas_sin_tasa: list[str]

    @property
    def fechas_de_corte(self) -> list[date]:
        return sorted({c.fecha_corte for c in self.cuentas if c.fecha_corte is not None})


def _convertir_usd_ves(
    saldo: Decimal, moneda: str, tasa_usd_ves: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    mon = (moneda or "").strip().upper()
    if mon in ("USD", "USDT"):
        usd: Decimal | None = _q2(saldo)
        ves: Decimal | None = _q2(saldo * tasa_usd_ves) if tasa_usd_ves and tasa_usd_ves > CERO else None
        return usd, ves
    if mon == "VES":
        usd_conv: Decimal | None = _q2(saldo / tasa_usd_ves) if tasa_usd_ves and tasa_usd_ves > CERO else None
        return usd_conv, _q2(saldo)
    return None, None


def _verificar_continuidad(cortes: list[CorteExtracto]) -> list[str]:
    alertas: list[str] = []
    ordenados = sorted(
        (c for c in cortes if c.fecha_desde is not None and c.fecha_hasta is not None),
        key=lambda c: (c.fecha_desde or date.min, c.fecha_hasta or date.min, c.cargado_en),
    )
    for prev, sig in zip(ordenados, ordenados[1:], strict=False):
        if prev.fecha_hasta is None or sig.fecha_desde is None:
            continue
        if sig.fecha_desde <= prev.fecha_hasta:
            continue  # Cortes solapados: la huella deduplica movimientos comunes.
        if prev.saldo_final is None or sig.saldo_inicial is None:
            continue
        if abs(sig.saldo_inicial - prev.saldo_final) > TOL:
            alertas.append(
                f"hueco entre {prev.fecha_hasta} y {sig.fecha_desde}: el corte "
                f"'{prev.nombre_archivo}' cierra en {_q2(prev.saldo_final)} y "
                f"'{sig.nombre_archivo}' abre en {_q2(sig.saldo_inicial)} "
                f"(Δ={_q2(sig.saldo_inicial - prev.saldo_final)})"
            )
    return alertas


def consolidar_cortes(
    cortes: list[CorteExtracto],
    resolvedor_tasa_usd_ves: Callable[[date], Decimal | None],
) -> ConsolidadoExtractos:
    """Consolida los cortes activos por cuenta bancaria convirtiendo a USD y VES."""
    por_cuenta: dict[str, list[CorteExtracto]] = defaultdict(list)
    for c in cortes:
        por_cuenta[c.cuenta_id].append(c)

    cuentas: list[SaldoCuentaExtracto] = []
    total_usd = CERO
    total_ves = CERO
    sin_tasa: list[str] = []

    for cuenta_id in sorted(
        por_cuenta,
        key=lambda cid: (por_cuenta[cid][0].nombre_banco.upper(), por_cuenta[cid][0].numero_cuenta),
    ):
        lista = por_cuenta[cuenta_id]
        ultimo = max(lista, key=lambda c: (c.fecha_hasta or date.min, c.cargado_en))
        tasa = resolvedor_tasa_usd_ves(ultimo.fecha_hasta) if ultimo.fecha_hasta else None
        usd: Decimal | None = None
        ves: Decimal | None = None
        if ultimo.saldo_final is not None:
            usd, ves = _convertir_usd_ves(ultimo.saldo_final, ultimo.moneda, tasa)

        alertas = _verificar_continuidad(lista)
        etiqueta_cta = f"{ultimo.nombre_banco} ({ultimo.numero_cuenta})"
        if ultimo.saldo_final is None:
            alertas.append("el archivo no informa saldo: la cuenta queda fuera del total")
        elif usd is None or ves is None:
            sin_tasa.append(etiqueta_cta)
        else:
            total_usd += usd
            total_ves += ves

        if not ultimo.cuadra:
            alertas.insert(0, f"el último corte ('{ultimo.nombre_archivo}') no cuadra")

        cuentas.append(
            SaldoCuentaExtracto(
                cuenta_id=cuenta_id,
                nombre_banco=ultimo.nombre_banco,
                numero_cuenta=ultimo.numero_cuenta,
                moneda=ultimo.moneda,
                fecha_corte=ultimo.fecha_hasta,
                saldo=_q2(ultimo.saldo_final) if ultimo.saldo_final is not None else None,
                tasa_usd_ves=tasa,
                saldo_usd=usd,
                saldo_ves=ves,
                n_cortes=len(lista),
                cortes_sin_cuadrar=sum(1 for c in lista if not c.cuadra),
                alertas=alertas,
            )
        )

    return ConsolidadoExtractos(
        cuentas=cuentas,
        total_usd=_q2(total_usd),
        total_ves=_q2(total_ves),
        cuentas_sin_tasa=sin_tasa,
    )
