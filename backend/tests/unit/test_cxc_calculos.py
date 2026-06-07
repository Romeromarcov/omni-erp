"""
Unit determinista (sin BD, sin hypothesis) de aging/scoring de cartera CxC.

Pensado como **runner de mutation testing** para
``apps/cuentas_por_cobrar/services_aging.py`` y ``services_scoring.py``: ejemplos
fijos y rápidos que fijan el valor exacto de cada rama (matar mutantes exige
aserciones sobre el valor, no solo "no explota"). El property-based exhaustivo vive
en ``test_property_cxc.py``; este complementa con casos por-ejemplo veloces.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.cuentas_por_cobrar.services_aging import (
    BUCKETS,
    PartidaCartera,
    _calcular_bucket,
    calcular_aging,
)
from apps.cuentas_por_cobrar.services_scoring import ScoreInput, calcular_score, priorizar

pytestmark = pytest.mark.unit


def _partida(dias: int, monto: str, idx: int = 0) -> PartidaCartera:
    return PartidaCartera(
        cliente_id=f"cli-{idx}",
        cliente_nombre=f"Cliente {idx}",
        orden_ref=f"ORD-{idx}",
        monto_total=Decimal(monto),
        monto_pendiente=Decimal(monto),
        fecha_vencimiento=date.today() - timedelta(days=dias),
        estado_pago="pendiente",
    )


# ── _calcular_bucket: cada rama con su frontera ─────────────────────────────────


def test_bucket_cada_rama():
    assert _calcular_bucket(-1) == "al_dia"
    assert _calcular_bucket(0) == "al_dia"
    assert _calcular_bucket(1) == "1_30"
    assert _calcular_bucket(30) == "1_30"
    assert _calcular_bucket(31) == "31_60"
    assert _calcular_bucket(60) == "31_60"
    assert _calcular_bucket(61) == "61_90"
    assert _calcular_bucket(90) == "61_90"
    assert _calcular_bucket(91) == "mas_90"


# ── calcular_aging: clasificación, sumas, conteos ───────────────────────────────


def test_aging_clasifica_y_suma():
    partidas = [
        _partida(0, "100.00", 0),    # al_dia
        _partida(15, "200.00", 1),   # 1_30
        _partida(45, "300.00", 2),   # 31_60
        _partida(75, "400.00", 3),   # 61_90
        _partida(120, "500.00", 4),  # mas_90
    ]
    res = calcular_aging(partidas)
    assert res["buckets"]["al_dia"] == {"count": 1, "total": "100.00"}
    assert res["buckets"]["1_30"] == {"count": 1, "total": "200.00"}
    assert res["buckets"]["31_60"] == {"count": 1, "total": "300.00"}
    assert res["buckets"]["61_90"] == {"count": 1, "total": "400.00"}
    assert res["buckets"]["mas_90"] == {"count": 1, "total": "500.00"}
    assert res["total_pendiente"] == "1500.00"
    assert res["total_partidas"] == 5
    # vencidas = todas menos la "al_dia"
    assert res["partidas_vencidas"] == 4


def test_aging_excluye_saldo_no_positivo():
    partidas = [_partida(45, "0", 0), _partida(45, "150.00", 1)]
    res = calcular_aging(partidas)
    assert res["total_pendiente"] == "150.00"
    assert sum(res["buckets"][b]["count"] for b in BUCKETS) == 1
    assert res["total_partidas"] == 2
    assert res["partidas_vencidas"] == 1


def test_aging_vacio():
    res = calcular_aging([])
    assert res["total_pendiente"] == "0"
    assert res["total_partidas"] == 0
    assert res["partidas_vencidas"] == 0
    assert all(res["buckets"][b] == {"count": 0, "total": "0"} for b in BUCKETS)


# ── calcular_score: fórmula exacta y cada término ───────────────────────────────


def test_score_formula_exacta():
    # 10*3 + 1000/100 + 2*5 = 30 + 10 + 10 = 50
    assert calcular_score(ScoreInput(10, Decimal("1000"), 2)) == Decimal("50")


def test_score_solo_dias():
    assert calcular_score(ScoreInput(7, Decimal("0"), 0)) == Decimal("21")


def test_score_solo_monto():
    assert calcular_score(ScoreInput(0, Decimal("250"), 0)) == Decimal("2.5")


def test_score_solo_intentos():
    assert calcular_score(ScoreInput(0, Decimal("0"), 4)) == Decimal("20")


def test_score_cero():
    assert calcular_score(ScoreInput(0, Decimal("0"), 0)) == Decimal("0")


# ── priorizar: filtra vencidas, ordena DESC ─────────────────────────────────────


def test_priorizar_filtra_y_ordena():
    partidas = [
        _partida(0, "9999.00", 0),   # al día → excluida
        _partida(10, "100.00", 1),   # vencida, score 30 + 1 = 31
        _partida(100, "100.00", 2),  # vencida, score 300 + 1 = 301
    ]
    resultado = priorizar(partidas)
    assert [r["cliente_id"] for r in resultado] == ["cli-2", "cli-1"]
    assert Decimal(resultado[0]["score"]) > Decimal(resultado[1]["score"])


def test_priorizar_usa_intentos_map():
    partidas = [_partida(10, "100.00", 1)]
    # score base 31 + intentos 3*5 = 46
    resultado = priorizar(partidas, intentos_map={"cli-1": 3})
    assert Decimal(resultado[0]["score"]) == Decimal("46")


def test_priorizar_sin_vencidas_es_vacio():
    assert priorizar([_partida(0, "500.00", 0)]) == []
