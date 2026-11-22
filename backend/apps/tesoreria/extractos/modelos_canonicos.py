"""Modelo canónico y validador matemático de estados de cuenta bancarios.

Desacoplado de cualquier empresa o banco particular: todo formato de estado de cuenta
se reduce a ``EstadoCuentaCanonico`` + ``LineaExtractoCanonica``, permitiendo validar
la cadena de saldos fila a fila y deduplicar cortes solapados por ``huella`` SHA-256.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

CERO = Decimal("0.00")
TOL = Decimal("0.01")


class ExtractoBancarioError(ValueError):
    """Error de dominio al leer, parsear o validar la pertenencia de un extracto."""


@dataclass(frozen=True)
class LineaExtractoCanonica:
    """Línea canónica normalizada de un estado de cuenta bancario."""

    formato_banco: str
    cuenta_clave: str
    moneda: str
    fecha: date
    referencia: str
    descripcion: str
    debito: Decimal
    credito: Decimal
    saldo: Decimal | None
    orden: int
    codigo: str = ""
    correlativo: str = ""

    @property
    def neto(self) -> Decimal:
        return self.credito - self.debito

    @property
    def tipo_movimiento(self) -> str:
        if self.credito > CERO and self.debito == CERO:
            return "CREDITO"
        if self.debito > CERO and self.credito == CERO:
            return "DEBITO"
        return "CREDITO" if self.neto >= CERO else "DEBITO"

    @property
    def monto_absoluto(self) -> Decimal:
        if self.credito > CERO and self.debito == CERO:
            return self.credito
        if self.debito > CERO and self.credito == CERO:
            return self.debito
        return abs(self.neto)

    @property
    def huella(self) -> str:
        """Hash estable de 24 hex para idempotencia ante cortes solapados.

        Con saldo reportado por el banco, el saldo distingue dos operaciones idénticas
        del mismo día sin depender del número de fila (Provincial renumera el
        correlativo al cambiar el rango exportado). Sin saldo (p. ej. Binance), usa
        ``correlativo`` estable (timestamp exacto) o ``orden`` dentro del corte.
        """
        if self.saldo is not None:
            distingue = f"{self.saldo:.2f}"
        elif self.correlativo:
            distingue = f"@{self.correlativo}"
        else:
            distingue = f"#{self.orden}"
        base = "|".join(
            [
                self.cuenta_clave,
                self.fecha.isoformat(),
                self.referencia,
                self.descripcion.strip().upper(),
                f"{self.debito:.2f}",
                f"{self.credito:.2f}",
                distingue,
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


@dataclass
class EstadoCuentaCanonico:
    """Estado de cuenta normalizado previo a persistencia."""

    formato_banco: str
    cuenta_clave: str
    moneda: str
    archivo: str
    movimientos: list[LineaExtractoCanonica] = field(default_factory=list)
    saldo_inicial: Decimal | None = None
    saldo_final: Decimal | None = None
    saldo_inicial_derivado: bool = False
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResultadoValidacion:
    """Resultado de verificar la cadena de saldos y duplicados de un extracto."""

    formato_banco: str
    archivo: str
    n_movimientos: int
    saldo_inicial: Decimal | None
    saldo_final_calculado: Decimal | None
    saldo_final_reportado: Decimal | None
    total_debitos: Decimal
    total_creditos: Decimal
    saltos: list[str] = field(default_factory=list)
    duplicados: list[str] = field(default_factory=list)
    ok: bool = True


def validar_estado(est: EstadoCuentaCanonico) -> ResultadoValidacion:
    """Verifica ``saldo_prev + credito - debito == saldo`` fila a fila (±0.01)."""
    res = ResultadoValidacion(
        formato_banco=est.formato_banco,
        archivo=est.archivo,
        n_movimientos=len(est.movimientos),
        saldo_inicial=est.saldo_inicial,
        saldo_final_calculado=None,
        saldo_final_reportado=est.saldo_final,
        total_debitos=sum((m.debito for m in est.movimientos), CERO),
        total_creditos=sum((m.credito for m in est.movimientos), CERO),
    )
    prev = est.saldo_inicial
    for m in est.movimientos:
        if m.saldo is not None and prev is not None:
            esperado = prev + m.neto
            if abs(esperado - m.saldo) > TOL:
                res.saltos.append(
                    f"#{m.orden} {m.fecha} ref={m.referencia} esperado={esperado} "
                    f"banco={m.saldo} (Δ={m.saldo - esperado})"
                )
        if m.saldo is not None:
            prev = m.saldo
        elif prev is not None:
            prev = prev + m.neto
    res.saldo_final_calculado = prev
    if est.saldo_final is not None and prev is not None and abs(est.saldo_final - prev) > TOL:
        res.saltos.append(f"saldo final declarado {est.saldo_final} != último saldo {prev}")

    vistos: dict[str, int] = {}
    for m in est.movimientos:
        vistos[m.huella] = vistos.get(m.huella, 0) + 1
    res.duplicados = [h for h, n in vistos.items() if n > 1]
    res.ok = not res.saltos and not res.duplicados
    return res
