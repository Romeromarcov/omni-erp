"""
Tests del motor de valoración de inventario (FIFO / Costo Promedio).

Cubre apps/inventario/valuation.py y su integración con registrar_movimiento():
  - ENTRADA crea capa de costo (ValoracionInventario sentido=ENTRADA).
  - SALIDA con método PROMEDIO costea al promedio ponderado de capas vivas.
  - SALIDA con método FIFO costea consumiendo las capas más antiguas primero.
  - TRANSFERENCIA traslada el costo de salida a la capa de destino.
  - SALIDA sin capas costeadas cae al costo_promedio del producto (respaldo).
  - AJUSTE negativo consume capas; el costo calculado fija costo_unitario_movimiento.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.almacenes.models import Almacen
from apps.inventario.models import (
    CategoriaProducto,
    Producto,
    StockActual,
    UnidadMedida,
    ValoracionInventario,
)
from apps.inventario.services import registrar_movimiento

pytestmark = pytest.mark.django_db


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def categoria(empresa_a):
    return CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="General")


@pytest.fixture
def unidad(empresa_a):
    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN", tipo="CANTIDAD"
    )


@pytest.fixture
def almacen_a(empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Central", codigo_almacen="ALM-A"
    )


@pytest.fixture
def almacen_b(empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Sucursal", codigo_almacen="ALM-B"
    )


def _producto(empresa_a, categoria, unidad, moneda_usd, metodo, costo_promedio="0.00"):
    return Producto.objects.create(
        id_empresa=empresa_a,
        id_categoria=categoria,
        id_unidad_medida_base=unidad,
        id_moneda_precio=moneda_usd,
        nombre_producto=f"Producto {metodo}",
        metodo_valoracion=metodo,
        costo_promedio=Decimal(costo_promedio),
    )


def _entrada(empresa_a, producto, almacen, user_a, cantidad, costo):
    return registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto,
        cantidad=Decimal(str(cantidad)),
        almacen_destino=almacen,
        costo_unitario=Decimal(str(costo)),
        usuario=user_a,
    )


# ── PROMEDIO ──────────────────────────────────────────────────────────────────


def test_promedio_costea_salida_al_promedio_ponderado(
    empresa_a, categoria, unidad, moneda_usd, almacen_a, user_a
):
    prod = _producto(empresa_a, categoria, unidad, moneda_usd, "PROMEDIO")
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "10.00")
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "20.00")

    salida = registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="SALIDA",
        producto=prod,
        cantidad=Decimal("5"),
        almacen_origen=almacen_a,
        usuario=user_a,
    )

    val = ValoracionInventario.objects.get(id_movimiento=salida, sentido="SALIDA")
    assert val.metodo == "PROMEDIO"
    assert val.costo_unitario == Decimal("15.0000")  # (10*10 + 10*20)/20
    assert val.valor_total == Decimal("75.0000")
    # El costo calculado se propaga al movimiento (para asientos COGS).
    salida.refresh_from_db()
    assert salida.costo_unitario_movimiento == Decimal("15.0000")


# ── FIFO ──────────────────────────────────────────────────────────────────────


def test_fifo_consume_capas_antiguas_primero(
    empresa_a, categoria, unidad, moneda_usd, almacen_a, user_a
):
    prod = _producto(empresa_a, categoria, unidad, moneda_usd, "FIFO")
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "10.00")
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "20.00")

    salida = registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="SALIDA",
        producto=prod,
        cantidad=Decimal("15"),
        almacen_origen=almacen_a,
        usuario=user_a,
    )

    val = ValoracionInventario.objects.get(id_movimiento=salida, sentido="SALIDA")
    assert val.metodo == "FIFO"
    # 10 @ 10 + 5 @ 20 = 200 ; 200/15 = 13.3333
    assert val.valor_total == Decimal("200.0000")
    assert val.costo_unitario == Decimal("13.3333")

    # La primera capa quedó agotada; la segunda con 5 unidades restantes.
    capas = list(
        ValoracionInventario.objects.filter(
            id_producto=prod, sentido="ENTRADA"
        ).order_by("fecha_creacion")
    )
    assert capas[0].cantidad_restante == Decimal("0.0000")
    assert capas[1].cantidad_restante == Decimal("5.0000")


# ── TRANSFERENCIA ─────────────────────────────────────────────────────────────


def test_transferencia_traslada_costo_a_destino(
    empresa_a, categoria, unidad, moneda_usd, almacen_a, almacen_b, user_a
):
    prod = _producto(empresa_a, categoria, unidad, moneda_usd, "PROMEDIO")
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "12.00")

    transfer = registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="TRANSFERENCIA",
        producto=prod,
        cantidad=Decimal("4"),
        almacen_origen=almacen_a,
        almacen_destino=almacen_b,
        usuario=user_a,
    )

    salida = ValoracionInventario.objects.get(id_movimiento=transfer, sentido="SALIDA")
    entrada = ValoracionInventario.objects.get(id_movimiento=transfer, sentido="ENTRADA")
    assert salida.id_almacen_id == almacen_a.pk
    assert entrada.id_almacen_id == almacen_b.pk
    assert salida.costo_unitario == Decimal("12.0000")
    assert entrada.costo_unitario == Decimal("12.0000")
    assert entrada.cantidad_restante == Decimal("4.0000")


# ── Respaldo: salida sin capas costeadas ──────────────────────────────────────


def test_salida_sin_capas_usa_costo_promedio_respaldo(
    empresa_a, categoria, unidad, moneda_usd, almacen_a, user_a
):
    prod = _producto(empresa_a, categoria, unidad, moneda_usd, "PROMEDIO", costo_promedio="7.00")
    # Stock existente sin capa de valoración (p. ej. saldo de apertura).
    StockActual.objects.create(
        id_empresa=empresa_a,
        id_producto=prod,
        id_almacen=almacen_a,
        cantidad_disponible=Decimal("10"),
    )

    salida = registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="SALIDA",
        producto=prod,
        cantidad=Decimal("5"),
        almacen_origen=almacen_a,
        usuario=user_a,
    )

    val = ValoracionInventario.objects.get(id_movimiento=salida, sentido="SALIDA")
    assert val.costo_unitario == Decimal("7.0000")
    assert val.valor_total == Decimal("35.0000")


# ── AJUSTE negativo ───────────────────────────────────────────────────────────


def test_ajuste_negativo_consume_capas_y_fija_costo(
    empresa_a, categoria, unidad, moneda_usd, almacen_a, user_a
):
    prod = _producto(empresa_a, categoria, unidad, moneda_usd, "FIFO")
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "5.00")

    ajuste = registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="AJUSTE",
        producto=prod,
        cantidad=Decimal("-3"),
        almacen_destino=almacen_a,
        usuario=user_a,
    )

    val = ValoracionInventario.objects.get(id_movimiento=ajuste, sentido="SALIDA")
    assert val.cantidad == Decimal("3.0000")
    assert val.costo_unitario == Decimal("5.0000")
    assert val.valor_total == Decimal("15.0000")
    ajuste.refresh_from_db()
    assert ajuste.costo_unitario_movimiento == Decimal("5.0000")


def test_ajuste_salida_asiento_monto_igual_valor_total(
    empresa_a, categoria, unidad, moneda_usd, almacen_a, user_a
):
    """ACCOUNTING: el asiento de un AJUSTE de salida usa exactamente valor_total."""
    from apps.contabilidad.models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas

    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    debe = PlanCuentas.objects.create(
        id_empresa=empresa_a, codigo_cuenta="6105", nombre_cuenta="Pérdida Ajuste",
        tipo_cuenta="GASTO", naturaleza="DEUDORA", nivel=1,
    )
    haber = PlanCuentas.objects.create(
        id_empresa=empresa_a, codigo_cuenta="1105", nombre_cuenta="Inventario",
        tipo_cuenta="ACTIVO", naturaleza="DEUDORA", nivel=1,
    )
    MapeoContable.objects.create(
        id_empresa=empresa_a, tipo_asiento="AJUSTE_INVENTARIO",
        cuenta_debe=debe, cuenta_haber=haber, activo=True,
    )

    prod = _producto(empresa_a, categoria, unidad, moneda_usd, "FIFO")
    # Costos que generan cociente no exacto: 10@10 + 10@20, salida 15 → 200/15.
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "10.00")
    _entrada(empresa_a, prod, almacen_a, user_a, 10, "20.00")

    ajuste = registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="AJUSTE",
        producto=prod,
        cantidad=Decimal("-15"),
        almacen_destino=almacen_a,
        usuario=user_a,
    )

    val = ValoracionInventario.objects.get(id_movimiento=ajuste, sentido="SALIDA")
    assert val.valor_total == Decimal("200.0000")
    asiento = AsientoContable.objects.get(id_documento_origen=ajuste.pk)
    total_debe = sum(d.debe for d in DetalleAsiento.objects.filter(id_asiento=asiento))
    total_haber = sum(d.haber for d in DetalleAsiento.objects.filter(id_asiento=asiento))
    # Asiento balanceado y monto == valor_total (a la precisión 2dp del asiento).
    assert total_debe == total_haber
    assert total_debe == val.valor_total.quantize(Decimal("0.01"))


def test_entrada_sin_costo_usa_costo_promedio(
    empresa_a, categoria, unidad, moneda_usd, almacen_a, user_a
):
    prod = _producto(empresa_a, categoria, unidad, moneda_usd, "PROMEDIO", costo_promedio="9.00")
    mov = registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=prod,
        cantidad=Decimal("5"),
        almacen_destino=almacen_a,
        usuario=user_a,
    )
    capa = ValoracionInventario.objects.get(id_movimiento=mov, sentido="ENTRADA")
    assert capa.costo_unitario == Decimal("9.0000")
    assert capa.cantidad_restante == Decimal("5.0000")
    # ENTRADA sin costo explícito no debe rellenar costo_unitario_movimiento.
    mov.refresh_from_db()
    assert mov.costo_unitario_movimiento is None
