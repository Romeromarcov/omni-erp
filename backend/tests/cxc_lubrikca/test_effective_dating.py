"""Tests unitarios del effective dating (portados de CxC_Lubrikca).

Construyen instancias de modelo EN MEMORIA (sin tocar la BD) para que sean
rápidos: las funciones son puras y operan por duck typing sobre los atributos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.cxc_lubrikca.models import (
    Condicion,
    DescuentoBCVCompleto,
    DescuentoMarcaCategoria,
    Feriado,
    MetodoPago,
    PromocionPrimeraCompra,
    ReglaRecurrencia,
    TipoBeneficio,
    TipoDescuento,
)
from apps.cxc_lubrikca.services.effective_dating import (
    descuento_vigente,
    promocion_primera_compra_vigente,
    regla_recurrencia_vigente,
    tasa_bcv_completo_vigente,
)

pytestmark = pytest.mark.unit


def _d(rid: str, marca: str, categoria: str, pct: str, *, desde=date(2026, 1, 1), hasta=None, activo=True):
    return DescuentoMarcaCategoria(
        id=rid,
        marca=marca,
        categoria=categoria,
        tipo_descuento=TipoDescuento.CONTADO,
        porcentaje=Decimal(pct),
        vigencia_desde=desde,
        vigencia_hasta=hasta,
        activo=activo,
    )


def _recompra(valor: str, *, desde, hasta=None, activo=True):
    return ReglaRecurrencia(
        id=f"rr-{valor}-{desde}",
        condicion=Condicion.RECOMPRA,
        tipo_beneficio=TipoBeneficio.PORCENTAJE,
        valor=Decimal(valor),
        vigencia_desde=desde,
        vigencia_hasta=hasta,
        activo=activo,
    )


# --- descuento_vigente -------------------------------------------------------
def test_descuento_categoria_exacta_gana_sobre_comodin():
    reglas = [
        _d("A", "Global Oil", "*", "0.06"),
        _d("B", "Global Oil", "Comercial sintéticos", "0.08"),
    ]
    elegido = descuento_vigente(
        reglas, marca="Global Oil", categoria="Comercial sintéticos",
        tipo=TipoDescuento.CONTADO, fecha=date(2026, 6, 1),
    )
    assert elegido is not None and elegido.id == "B"


def test_descuento_marca_exacta_gana_sobre_marca_comodin():
    reglas = [
        _d("A", "*", "Lubricantes", "0.05"),  # especificidad 1
        _d("B", "Sinoco", "*", "0.04"),  # especificidad 2 (marca exacta pesa más)
    ]
    elegido = descuento_vigente(
        reglas, marca="Sinoco", categoria="Lubricantes",
        tipo=TipoDescuento.CONTADO, fecha=date(2026, 6, 1),
    )
    assert elegido is not None and elegido.id == "B"


def test_descuento_empate_rompe_por_menor_porcentaje_luego_id():
    # Misma especificidad ('*','*'); gana el conservador (menor %), luego str(id).
    reglas = [
        _d("Z", "*", "*", "0.05"),
        _d("A", "*", "*", "0.03"),
        _d("M", "*", "*", "0.03"),
    ]
    elegido = descuento_vigente(
        reglas, marca="X", categoria="Y",
        tipo=TipoDescuento.CONTADO, fecha=date(2026, 6, 1),
    )
    # Menor porcentaje es 0.03 (A y M); desempata str(id): "A" < "M".
    assert elegido is not None and elegido.id == "A"


def test_descuento_fuera_de_vigencia_no_aplica():
    regla = _d("A", "Sinoco", "*", "0.03", hasta=date(2026, 3, 1))
    elegido = descuento_vigente(
        [regla], marca="Sinoco", categoria="*", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    )
    assert elegido is None


def test_descuento_antes_de_vigencia_desde_no_aplica():
    regla = _d("A", "Sinoco", "*", "0.03", desde=date(2026, 7, 1))
    elegido = descuento_vigente(
        [regla], marca="Sinoco", categoria="*", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    )
    assert elegido is None


def test_descuento_inactivo_no_aplica():
    regla = _d("A", "Sinoco", "*", "0.03", activo=False)
    elegido = descuento_vigente(
        [regla], marca="Sinoco", categoria="*", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    )
    assert elegido is None


def test_descuento_sin_match_devuelve_none():
    assert descuento_vigente(
        [], marca="X", categoria="Y", tipo=TipoDescuento.CONTADO,
        fecha=date(2026, 6, 1),
    ) is None


# --- promocion_primera_compra_vigente ---------------------------------------
def test_promocion_selecciona_la_mas_reciente():
    vieja = PromocionPrimeraCompra(id="p1", producto="Liga vieja", vigencia_desde=date(2026, 1, 1))
    nueva = PromocionPrimeraCompra(id="p2", producto="Liga nueva", vigencia_desde=date(2026, 5, 1))
    elegido = promocion_primera_compra_vigente([vieja, nueva], fecha=date(2026, 6, 1))
    assert elegido is not None and elegido.producto == "Liga nueva"


def test_promocion_sin_vigente_none():
    promo = PromocionPrimeraCompra(
        id="p1", producto="Liga", vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 3, 1),
    )
    assert promocion_primera_compra_vigente([promo], fecha=date(2026, 6, 1)) is None
    assert promocion_primera_compra_vigente([], fecha=date(2026, 6, 1)) is None


# --- tasa_bcv_completo_vigente ----------------------------------------------
def test_bcv_completo_gana_vigencia_mas_reciente():
    vieja = DescuentoBCVCompleto(id="b1", porcentaje=Decimal("0.02"), vigencia_desde=date(2026, 1, 1))
    nueva = DescuentoBCVCompleto(id="b2", porcentaje=Decimal("0.05"), vigencia_desde=date(2026, 5, 1))
    assert tasa_bcv_completo_vigente([vieja, nueva], fecha=date(2026, 6, 1)) == Decimal("0.05")


def test_bcv_completo_empate_fecha_gana_menor_porcentaje():
    a = DescuentoBCVCompleto(id="b1", porcentaje=Decimal("0.05"), vigencia_desde=date(2026, 5, 1))
    b = DescuentoBCVCompleto(id="b2", porcentaje=Decimal("0.03"), vigencia_desde=date(2026, 5, 1))
    assert tasa_bcv_completo_vigente([a, b], fecha=date(2026, 6, 1)) == Decimal("0.03")


def test_bcv_completo_sin_config_none():
    assert tasa_bcv_completo_vigente([], fecha=date(2026, 6, 1)) is None


# --- regla_recurrencia_vigente ----------------------------------------------
def test_recurrencia_vigente_selecciona_mas_reciente():
    vieja = _recompra("0.03", desde=date(2026, 1, 1))
    nueva = _recompra("0.04", desde=date(2026, 5, 1))
    elegido = regla_recurrencia_vigente(
        [vieja, nueva], condicion=Condicion.RECOMPRA, fecha=date(2026, 6, 1),
    )
    assert elegido is not None and elegido.valor == Decimal("0.04")


def test_recurrencia_empate_fecha_gana_menor_valor():
    a = _recompra("0.05", desde=date(2026, 5, 1))
    b = _recompra("0.03", desde=date(2026, 5, 1))
    elegido = regla_recurrencia_vigente(
        [a, b], condicion=Condicion.RECOMPRA, fecha=date(2026, 6, 1),
    )
    assert elegido is not None and elegido.valor == Decimal("0.03")


def test_recurrencia_filtra_por_condicion():
    recompra = _recompra("0.04", desde=date(2026, 1, 1))
    elegido = regla_recurrencia_vigente(
        [recompra], condicion=Condicion.PRIMERA_COMPRA, fecha=date(2026, 6, 1),
    )
    assert elegido is None


def test_recurrencia_sin_match_none():
    assert regla_recurrencia_vigente(
        [], condicion=Condicion.PRIMERA_COMPRA, fecha=date(2026, 6, 1)
    ) is None


# --- modelos: __str__ e is_deleted (puro, sin BD) ---------------------------
def test_str_de_modelos():
    assert "Sinoco" in str(_d("A", "Sinoco", "*", "0.03"))
    assert "BCV-completo" in str(
        DescuentoBCVCompleto(porcentaje=Decimal("0.05"), vigencia_desde=date(2026, 1, 1))
    )
    assert "Liga" in str(
        PromocionPrimeraCompra(producto="Liga", vigencia_desde=date(2026, 1, 1))
    )
    assert "recompra" in str(_recompra("0.04", desde=date(2026, 1, 1)))
    assert "Carnaval" in str(
        Feriado(fecha=date(2026, 2, 16), descripcion="Carnaval")
    )
    assert "ZELLE" in str(MetodoPago(codigo="ZELLE", nombre="Zelle"))


def test_is_deleted_property():
    d = _d("A", "Sinoco", "*", "0.03")
    assert d.is_deleted is False
    from django.utils import timezone

    d.deleted_at = timezone.now()
    assert d.is_deleted is True
