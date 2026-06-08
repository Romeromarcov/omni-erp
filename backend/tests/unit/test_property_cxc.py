"""
TEST-3 (ampliación) — Property-based (hypothesis) de invariantes de cartera CxC.

Ejercita las funciones puras de aging y scoring de ``cuentas_por_cobrar`` —sin BD—
sobre miles de carteras generadas, verificando invariantes que deben cumplirse
SIEMPRE:

- aging: el total reportado es exactamente la suma por bucket; los conteos cuadran;
  ningún total es negativo; el bucket asignado corresponde a los días de vencido.
- scoring: la fórmula es monótona no decreciente en cada entrada y no negativa para
  entradas no negativas; ``priorizar`` sólo devuelve vencidas, ordenadas DESC.

Complementa ``tests_api/test_property_fiscal.py`` (IVA/IGTF) extendiendo el
property-based a la matemática de cobranza, que el plan listaba como pendiente.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.cuentas_por_cobrar.services_aging import (
    BUCKETS,
    PartidaCartera,
    _calcular_bucket,
    calcular_aging,
)
from apps.cuentas_por_cobrar.services_scoring import ScoreInput, calcular_score, priorizar

pytestmark = pytest.mark.unit


# Días de vencido: negativos (al día / por vencer) y positivos (vencidos), acotados.
dias_strategy = st.integers(min_value=-365, max_value=3650)
# Montos pendientes no negativos, hasta 10 millones, 2 decimales.
montos_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("10000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def _partida(dias: int, monto: Decimal, idx: int = 0) -> PartidaCartera:
    """Construye una PartidaCartera con ``dias_vencida == dias`` exactos.

    ``fecha_vencimiento = hoy - dias`` ⇒ ``(hoy - fecha).days == dias`` en
    __post_init__, lo que además ejercita el cálculo de bucket/vencida real.
    """
    return PartidaCartera(
        cliente_id=f"cli-{idx}",
        cliente_nombre=f"Cliente {idx}",
        orden_ref=f"ORD-{idx}",
        monto_total=monto,
        monto_pendiente=monto,
        fecha_vencimiento=date.today() - timedelta(days=dias),
        estado_pago="pendiente",
    )


# ── Bucket: frontera exacta ────────────────────────────────────────────────────

@given(dias=dias_strategy)
def test_bucket_pertenece_al_catalogo(dias):
    assert _calcular_bucket(dias) in BUCKETS


def test_bucket_fronteras_exactas():
    # Límites declarados en _calcular_bucket: <=0, <=30, <=60, <=90, resto.
    assert _calcular_bucket(0) == "al_dia"
    assert _calcular_bucket(-5) == "al_dia"
    assert _calcular_bucket(1) == "1_30"
    assert _calcular_bucket(30) == "1_30"
    assert _calcular_bucket(31) == "31_60"
    assert _calcular_bucket(60) == "31_60"
    assert _calcular_bucket(61) == "61_90"
    assert _calcular_bucket(90) == "61_90"
    assert _calcular_bucket(91) == "mas_90"


# ── Aging: sumas e invariantes de conteo ───────────────────────────────────────

@settings(max_examples=300)
@given(
    cartera=st.lists(
        st.tuples(dias_strategy, montos_strategy),
        min_size=0,
        max_size=40,
    )
)
def test_aging_total_es_suma_de_buckets(cartera):
    partidas = [_partida(d, m, i) for i, (d, m) in enumerate(cartera)]
    res = calcular_aging(partidas)

    suma_buckets = sum(Decimal(res["buckets"][b]["total"]) for b in BUCKETS)
    assert Decimal(res["total_pendiente"]) == suma_buckets

    # Ningún bucket aporta total negativo ni cuenta negativa.
    for b in BUCKETS:
        assert Decimal(res["buckets"][b]["total"]) >= 0
        assert res["buckets"][b]["count"] >= 0

    # total_partidas == TODAS las partidas (con o sin saldo).
    assert res["total_partidas"] == len(partidas)

    # Los conteos por bucket suman exactamente las partidas con saldo > 0.
    con_saldo = [p for p in partidas if p.monto_pendiente > 0]
    assert sum(res["buckets"][b]["count"] for b in BUCKETS) == len(con_saldo)

    # partidas_vencidas: vencidas con saldo > 0; nunca excede las que tienen saldo.
    esperadas_vencidas = sum(1 for p in con_saldo if p.vencida)
    assert res["partidas_vencidas"] == esperadas_vencidas
    assert res["partidas_vencidas"] <= len(con_saldo)


def test_aging_cartera_vacia():
    res = calcular_aging([])
    assert Decimal(res["total_pendiente"]) == 0
    assert res["total_partidas"] == 0
    assert res["partidas_vencidas"] == 0
    assert all(res["buckets"][b]["count"] == 0 for b in BUCKETS)


def test_aging_ignora_saldo_cero_o_negativo():
    # Partidas sin saldo no entran a ningún bucket ni al total pendiente.
    partidas = [_partida(45, Decimal("0"), 0), _partida(45, Decimal("100.00"), 1)]
    res = calcular_aging(partidas)
    assert Decimal(res["total_pendiente"]) == Decimal("100.00")
    assert sum(res["buckets"][b]["count"] for b in BUCKETS) == 1
    assert res["total_partidas"] == 2


# ── Scoring: fórmula, no-negatividad y monotonía ───────────────────────────────

@given(
    dias=st.integers(min_value=0, max_value=3650),
    monto=montos_strategy,
    intentos=st.integers(min_value=0, max_value=100),
)
def test_score_formula_exacta_y_no_negativa(dias, monto, intentos):
    score = calcular_score(ScoreInput(dias, monto, intentos))
    esperado = Decimal(dias) * 3 + monto / Decimal("100") + Decimal(intentos) * 5
    assert score == esperado
    assert score >= 0


@given(
    dias=st.integers(min_value=0, max_value=3650),
    monto=montos_strategy,
    intentos=st.integers(min_value=0, max_value=100),
    delta=st.integers(min_value=1, max_value=500),
)
def test_score_monotono_en_cada_entrada(dias, monto, intentos, delta):
    base = calcular_score(ScoreInput(dias, monto, intentos))
    # Subir cualquier dimensión nunca baja el score.
    assert calcular_score(ScoreInput(dias + delta, monto, intentos)) >= base
    assert calcular_score(ScoreInput(dias, monto + Decimal(delta), intentos)) >= base
    assert calcular_score(ScoreInput(dias, monto, intentos + delta)) >= base


@settings(max_examples=200)
@given(
    cartera=st.lists(st.tuples(dias_strategy, montos_strategy), min_size=0, max_size=30),
)
def test_priorizar_solo_vencidas_y_ordenadas_desc(cartera):
    partidas = [_partida(d, m, i) for i, (d, m) in enumerate(cartera)]
    resultado = priorizar(partidas)

    # Sólo entran las vencidas (dias_vencida > 0).
    assert len(resultado) == sum(1 for p in partidas if p.vencida)

    # Orden descendente estricto-o-igual por score.
    scores = [Decimal(r["score"]) for r in resultado]
    assert scores == sorted(scores, reverse=True)
