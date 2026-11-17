"""Tests unitarios de monotonicidad y formato RFC 9562 para ``apps.core.uuid.uuid7``."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import uuid

import apps.core.uuid as uuid_mod
from apps.core.uuid import uuid7


def test_uuid7_cumple_layout_rfc9562() -> None:
    generado = uuid7()
    assert isinstance(generado, uuid.UUID)
    assert generado.version == 7
    assert generado.variant == uuid.RFC_4122


def test_uuid7_estrictamente_monotono_mismo_milisegundo_y_rollover(monkeypatch) -> None:
    """Con reloj congelado, 5.000 llamadas seguidas (forzando rollover de 12 bits) crecen estrictamente."""
    reloj_fijo_s = 1_795_000_000.123
    monkeypatch.setattr(uuid_mod.time, "time", lambda: reloj_fijo_s)
    monkeypatch.setattr(uuid_mod, "_last_ts_ms", 0)
    monkeypatch.setattr(uuid_mod, "_counter", 0)

    secuencia = [uuid7() for _ in range(5_000)]
    assert secuencia == sorted(secuencia)
    assert len(set(secuencia)) == 5_000


def test_uuid7_resiste_retroceso_de_reloj(monkeypatch) -> None:
    """Si el reloj del sistema retrocede unos ms, uuid7 no retrocede su orden."""
    tiempos = iter([1_795_000_010.500, 1_795_000_010.495, 1_795_000_010.490])
    monkeypatch.setattr(uuid_mod.time, "time", lambda: next(tiempos))
    monkeypatch.setattr(uuid_mod, "_last_ts_ms", 0)
    monkeypatch.setattr(uuid_mod, "_counter", 0)

    u1, u2, u3 = uuid7(), uuid7(), uuid7()
    assert u1 < u2 < u3


def test_uuid7_unicidad_y_orden_bajo_concurrencia() -> None:
    """Múltiples hilos generando UUIDs en paralelo nunca colisionan."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(lambda _: uuid7(), range(2_000)))

    assert len(set(resultados)) == 2_000
    assert all(u.version == 7 for u in resultados)
