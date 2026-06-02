"""Ola 5.3 — Tests del núcleo puro de manufactura (BOM, MRP, costeo). Sin BD."""
from decimal import Decimal

import pytest

from apps.manufactura.services import (
    ComponenteBOM,
    ManufacturaError,
    RequerimientoMaterial,
    calcular_costo_produccion,
    calcular_mrp,
    explotar_bom,
)


def D(x):
    return Decimal(str(x))


# ── Explosión de BOM ──────────────────────────────────────────────────────────


def test_explotar_bom_simple():
    bom = [
        ComponenteBOM("madera", D("2")),
        ComponenteBOM("tornillo", D("8")),
    ]
    reqs = {r.producto_id: r.cantidad for r in explotar_bom(bom, D("5"))}
    assert reqs["madera"] == D("10")
    assert reqs["tornillo"] == D("40")


def test_explotar_bom_agrega_componentes_repetidos():
    bom = [ComponenteBOM("madera", D("2")), ComponenteBOM("madera", D("3"))]
    reqs = {r.producto_id: r.cantidad for r in explotar_bom(bom, D("4"))}
    assert reqs["madera"] == D("20")  # (2+3) * 4


def test_explotar_bom_excluye_opcionales_por_defecto():
    bom = [ComponenteBOM("base", D("1")), ComponenteBOM("barniz", D("1"), es_opcional=True)]
    reqs = {r.producto_id: r.cantidad for r in explotar_bom(bom, D("3"))}
    assert "barniz" not in reqs
    reqs2 = {r.producto_id: r.cantidad for r in explotar_bom(bom, D("3"), incluir_opcionales=True)}
    assert reqs2["barniz"] == D("3")


def test_explotar_bom_cantidad_invalida():
    with pytest.raises(ManufacturaError):
        explotar_bom([ComponenteBOM("x", D("1"))], D("0"))


# ── MRP ───────────────────────────────────────────────────────────────────────


def test_mrp_calcula_faltante():
    reqs = [RequerimientoMaterial("madera", D("10")), RequerimientoMaterial("tornillo", D("40"))]
    stock = {"madera": D("3"), "tornillo": D("50")}
    res = {f.producto_id: f for f in calcular_mrp(reqs, stock)}
    assert res["madera"].a_comprar == D("7")    # 10 - 3
    assert res["tornillo"].a_comprar == D("0")  # 40 - 50 → 0 (sobra)


def test_mrp_sin_stock():
    reqs = [RequerimientoMaterial("madera", D("10"))]
    res = calcular_mrp(reqs, {})
    assert res[0].a_comprar == D("10")
    assert res[0].disponible == D("0")


# ── Costeo ──────────────────────────────────────────────────────────────────


def test_costo_produccion_materiales_mano_obra_indirectos():
    consumos = [(D("100"), D("2")), (D("5"), D("8"))]  # 200 + 40 = 240 materiales
    costo = calcular_costo_produccion(
        consumos, mano_obra=D("60"), costos_indirectos=D("20"), cantidad_producida=D("4")
    )
    assert costo["costo_materiales"] == D("240")
    assert costo["costo_total"] == D("320")          # 240 + 60 + 20
    assert costo["costo_unitario"] == D("80.0000")   # 320 / 4


def test_costo_produccion_sin_extras():
    costo = calcular_costo_produccion([(D("10"), D("3"))], cantidad_producida=D("3"))
    assert costo["costo_total"] == D("30")
    assert costo["costo_unitario"] == D("10.0000")


def test_costo_produccion_cantidad_invalida():
    with pytest.raises(ManufacturaError):
        calcular_costo_produccion([(D("10"), D("1"))], cantidad_producida=D("0"))
