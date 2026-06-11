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


def test_priorizar_forma_exacta_del_dict():
    """Cada campo del dict de salida con su valor exacto (mata mutantes de campos)."""
    res = priorizar([_partida(10, "100.00", 7)])
    assert res == [{
        "cliente_id": "cli-7",
        "cliente_nombre": "Cliente 7",
        "orden_ref": "ORD-7",
        "monto_pendiente": "100.00",
        "dias_vencida": 10,
        "bucket": "1_30",
        "score": "31.00",
    }]


# ── PartidaCartera.__post_init__: normalizaciones y derivados ───────────────────


def test_post_init_sin_fecha_vencimiento():
    p = PartidaCartera(
        cliente_id="c", cliente_nombre="C", orden_ref="O",
        monto_total=Decimal("10"), monto_pendiente=Decimal("10"),
        fecha_vencimiento=None, estado_pago="x",
    )
    assert p.dias_vencida == 0
    assert p.vencida is False
    assert p.bucket == "al_dia"


def test_post_init_normaliza_montos_no_decimal():
    p = PartidaCartera(
        cliente_id="c", cliente_nombre="C", orden_ref="O",
        monto_total="123.45", monto_pendiente=None,
        fecha_vencimiento=None, estado_pago="x",
    )
    assert p.monto_total == Decimal("123.45")
    assert isinstance(p.monto_total, Decimal)
    # None → Decimal("0") (rama `or 0`)
    assert p.monto_pendiente == Decimal("0")


def test_post_init_vencida_es_estrictamente_mayor_que_cero():
    hoy_vence = _partida(0, "10.00")
    assert hoy_vence.vencida is False
    ayer = _partida(1, "10.00")
    assert ayer.vencida is True
    assert ayer.dias_vencida == 1


# ── PartidaCartera.from_omni (stub sin BD) ──────────────────────────────────────


class _AbonosStub:
    """Imita el related manager `cxc.abonos` sin tocar BD."""

    def __init__(self, total):
        self._total = total

    def aggregate(self, **kwargs):
        return {"t": self._total}


class _CxcStub:
    def __init__(self, monto, abonado, referencia_externa="REF-1", pk=99):
        self.cliente_ref = "cli-omni"
        self.cliente_display = "Cliente Omni"
        self.referencia_externa = referencia_externa
        self.pk = pk
        self.monto = monto
        self.fecha_vencimiento = date.today() - timedelta(days=40)
        self.estado = "pendiente"
        self.abonos = _AbonosStub(abonado)


def test_from_omni_resta_abonos_del_saldo():
    p = PartidaCartera.from_omni(_CxcStub(Decimal("100.00"), Decimal("30.00")))
    assert p.monto_total == Decimal("100.00")
    assert p.monto_pendiente == Decimal("70.00")
    assert p.cliente_id == "cli-omni"
    assert p.cliente_nombre == "Cliente Omni"
    assert p.orden_ref == "REF-1"
    assert p.estado_pago == "pendiente"
    assert p.bucket == "31_60"


def test_from_omni_sin_abonos_usa_cero():
    """aggregate → None debe tratarse como 0 (rama `or Decimal('0')`)."""
    p = PartidaCartera.from_omni(_CxcStub(Decimal("100.00"), None))
    assert p.monto_pendiente == Decimal("100.00")


def test_from_omni_sin_referencia_usa_pk():
    p = PartidaCartera.from_omni(
        _CxcStub(Decimal("50.00"), Decimal("0"), referencia_externa=None, pk=1234)
    )
    assert p.orden_ref == "1234"


# ── PartidaCartera.from_hub_dict ────────────────────────────────────────────────


def test_from_hub_dict_completo():
    vcto = date.today() - timedelta(days=5)
    p = PartidaCartera.from_hub_dict({
        "cliente_id": 42,
        "cliente_nombre": "Hub Cliente",
        "orden_ref": "SO-9",
        "monto_total": "250.50",
        "monto_pendiente": "200.25",
        "fecha_vencimiento": vcto.strftime("%Y-%m-%d"),
        "estado_pago": "open",
    })
    assert p.cliente_id == "42"
    assert p.cliente_nombre == "Hub Cliente"
    assert p.orden_ref == "SO-9"
    assert p.monto_total == Decimal("250.50")
    assert p.monto_pendiente == Decimal("200.25")
    assert p.fecha_vencimiento == vcto
    assert p.dias_vencida == 5
    assert p.vencida is True


def test_from_hub_dict_fecha_como_date():
    vcto = date.today() - timedelta(days=3)
    p = PartidaCartera.from_hub_dict({"fecha_vencimiento": vcto, "monto_pendiente": "1"})
    assert p.fecha_vencimiento == vcto
    assert p.dias_vencida == 3


def test_from_hub_dict_fecha_datetime_iso_trunca_a_10():
    vcto = date.today() - timedelta(days=2)
    p = PartidaCartera.from_hub_dict(
        {"fecha_vencimiento": f"{vcto.isoformat()} 15:30:00", "monto_pendiente": "1"}
    )
    assert p.fecha_vencimiento == vcto


def test_from_hub_dict_fecha_invalida_queda_none():
    p = PartidaCartera.from_hub_dict({"fecha_vencimiento": "no-fecha-xx", "monto_pendiente": "1"})
    assert p.fecha_vencimiento is None
    assert p.dias_vencida == 0
    assert p.bucket == "al_dia"


def test_from_hub_dict_defaults_con_dict_vacio():
    p = PartidaCartera.from_hub_dict({})
    assert p.cliente_id == ""
    assert p.cliente_nombre == ""
    assert p.orden_ref == ""
    assert p.monto_total == Decimal("0")
    assert p.monto_pendiente == Decimal("0")
    assert p.fecha_vencimiento is None
    assert p.estado_pago == ""
