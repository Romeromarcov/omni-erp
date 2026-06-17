"""
1.G — Comisiones de vendedores: devengo, anulación y liquidación (integration).

Reglas verificadas con montos calculados A MANO (R-CODE-4, Decimal exacto):

  - Al ENTREGAR una NotaVenta con vendedor y esquema vigente se devenga la
    comisión en la MISMA transacción (% base sobre el subtotal sin impuestos,
    con override por categoría de producto).
  - Sin vendedor / sin esquema vigente / esquema de otra empresa → no se
    devenga (la venta procede igual).
  - El devengo es idempotente (OneToOne nota↔comisión).
  - Anular la venta anula su comisión; si ya fue LIQUIDADA, la anulación
    falla con error controlado y nada cambia.
  - ``liquidar_comisiones`` marca DEVENGADA→LIQUIDADA solo dentro del período
    y es naturalmente idempotente (segunda corrida → 0).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ventas.models import (
    ComisionVenta,
    DetalleNotaVenta,
    EsquemaComision,
    EsquemaComisionCategoria,
    NotaVenta,
)
from apps.ventas.services import (
    VentaError,
    anular_comision_de_nota_venta,
    devengar_comision_venta,
    entregar_nota_venta,
    liquidar_comisiones,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Fixtures de escenario ─────────────────────────────────────────────────────


@pytest.fixture
def cliente(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Comisiones C.A.",
        rif="J-77001122-3",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Comisiones",
        codigo_almacen="ALM-COM",
    )


@pytest.fixture
def categorias(db, empresa_a):
    from apps.inventario.models import CategoriaProducto

    return {
        "ferreteria": CategoriaProducto.objects.create(
            id_empresa=empresa_a, nombre_categoria="Ferretería"
        ),
        "electricidad": CategoriaProducto.objects.create(
            id_empresa=empresa_a, nombre_categoria="Electricidad"
        ),
    }


@pytest.fixture
def productos(db, empresa_a, moneda_usd, categorias):
    from apps.inventario.models import Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-COM", tipo="CANTIDAD"
    )
    martillo = Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Martillo",
        id_unidad_medida_base=unidad,
        id_categoria=categorias["ferreteria"],
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("10.00"),
    )
    cable = Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Cable",
        id_unidad_medida_base=unidad,
        id_categoria=categorias["electricidad"],
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("5.00"),
    )
    return {"martillo": martillo, "cable": cable}


@pytest.fixture
def stock(db, empresa_a, productos, almacen, user_a):
    from apps.inventario.services import registrar_movimiento

    for producto in productos.values():
        registrar_movimiento(
            empresa=empresa_a,
            fecha_hora_movimiento=timezone.now(),
            tipo_movimiento="ENTRADA",
            producto=producto,
            cantidad=Decimal("1000"),
            almacen_destino=almacen,
            usuario=user_a,
        )


@pytest.fixture
def vendedor(db, empresa_a):
    from tests.factories import UsuariosFactory

    return UsuariosFactory(username="vendedor_juan", empresa=empresa_a)


@pytest.fixture
def esquema_5(db, empresa_a, vendedor):
    """Esquema base 5% sin vigencia (siempre aplica)."""
    return EsquemaComision.objects.create(
        id_empresa=empresa_a, vendedor=vendedor, porcentaje_base=Decimal("5.0000")
    )


_SEQ = iter(range(1, 10_000))


def _crear_nota(empresa, cliente, vendedor=None, lineas=None, fecha=None):
    """Nota BORRADOR con líneas [(producto, cantidad, precio_unitario), ...]."""
    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        id_vendedor=vendedor,
        numero_nota=f"NV-COM-{next(_SEQ):04d}",
        fecha_nota=fecha or timezone.localdate(),
        estado="BORRADOR",
    )
    for producto, cantidad, precio in lineas or []:
        DetalleNotaVenta.objects.create(
            id_nota_venta=nota,
            id_producto=producto,
            cantidad=cantidad,
            precio_unitario=precio,
            subtotal=cantidad * precio,
        )
    return nota


# ── Devengo: cálculo con montos a mano ────────────────────────────────────────


def test_repr_de_modelos_de_comision(empresa_a, cliente, vendedor, esquema_5, categorias):
    """__str__ legibles (aparecen en admin y logs)."""
    override = EsquemaComisionCategoria.objects.create(
        esquema=esquema_5, categoria=categorias["ferreteria"], porcentaje=Decimal("10.0000")
    )
    nota = _crear_nota(empresa_a, cliente, vendedor)
    comision = ComisionVenta.objects.create(
        id_empresa=empresa_a,
        vendedor=vendedor,
        nota_venta=nota,
        esquema=esquema_5,
        base_comisionable=Decimal("100.0000"),
        monto=Decimal("5.0000"),
        fecha_devengo=timezone.localdate(),
    )
    assert "5.0000" in str(esquema_5)
    assert "Ferretería" in str(override)
    assert "DEVENGADA" in str(comision)


def test_entrega_devenga_comision_porcentaje_base(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor, esquema_5, moneda_usd
):
    """2 líneas: 10 × 10.00 + 11 × 5.50 = 160.50 → 5% = 8.0250 exacto."""
    nota = _crear_nota(
        empresa_a,
        cliente,
        vendedor,
        [
            (productos["martillo"], Decimal("10"), Decimal("10.00")),
            (productos["cable"], Decimal("11"), Decimal("5.50")),
        ],
    )

    resultado = entregar_nota_venta(nota, almacen, user_a)

    comision = resultado["comision"]
    assert comision is not None
    assert comision.estado == "DEVENGADA"
    assert comision.id_empresa == empresa_a
    assert comision.vendedor == vendedor
    assert comision.esquema == esquema_5
    assert comision.base_comisionable == Decimal("160.5000")
    # 160.50 * 5 / 100 = 8.0250
    assert comision.monto == Decimal("8.0250")
    assert comision.id_moneda == moneda_usd
    assert comision.fecha_devengo == nota.fecha_nota
    # Desglose auditable por línea (montos como string, nunca float)
    assert [d["monto"] for d in comision.detalle_json] == ["5.0000", "3.0250"]


def test_override_por_categoria_aplica_su_porcentaje(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor, esquema_5, categorias
):
    """Ferretería tiene override 10%; Electricidad usa el base 5%."""
    EsquemaComisionCategoria.objects.create(
        esquema=esquema_5, categoria=categorias["ferreteria"], porcentaje=Decimal("10.0000")
    )
    nota = _crear_nota(
        empresa_a,
        cliente,
        vendedor,
        [
            (productos["martillo"], Decimal("2"), Decimal("100.00")),  # 200.00 al 10% = 20.0000
            (productos["cable"], Decimal("4"), Decimal("25.00")),  # 100.00 al 5%  =  5.0000
        ],
    )

    comision = entregar_nota_venta(nota, almacen, user_a)["comision"]

    assert comision.base_comisionable == Decimal("300.0000")
    assert comision.monto == Decimal("25.0000")
    porcentajes = {d["id_producto"]: d["porcentaje"] for d in comision.detalle_json}
    assert porcentajes[str(productos["martillo"].id_producto)] == "10.0000"
    assert porcentajes[str(productos["cable"].id_producto)] == "5.0000"


def test_redondeo_half_up_a_4_decimales(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor, esquema_5
):
    """3.3333 × 10.00 = 33.3330 → 5% = 1.666650 → quantize(0.0001) = 1.6667 (HALF_UP)."""
    nota = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["martillo"], Decimal("3.3333"), Decimal("10.00"))]
    )

    comision = entregar_nota_venta(nota, almacen, user_a)["comision"]

    assert comision.monto == Decimal("1.6667")


def test_sin_vendedor_no_devenga(empresa_a, cliente, almacen, productos, stock, user_a, esquema_5):
    nota = _crear_nota(
        empresa_a, cliente, None, [(productos["martillo"], Decimal("1"), Decimal("10.00"))]
    )

    resultado = entregar_nota_venta(nota, almacen, user_a)

    assert resultado["comision"] is None
    assert ComisionVenta.objects.count() == 0
    nota.refresh_from_db()
    assert nota.estado == "ENTREGADA"  # la venta procede igual


def test_sin_esquema_vigente_no_devenga(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor
):
    """Esquema con vigencia vencida ayer → no aplica hoy."""
    EsquemaComision.objects.create(
        id_empresa=empresa_a,
        vendedor=vendedor,
        porcentaje_base=Decimal("5.0000"),
        vigente_hasta=timezone.localdate() - timedelta(days=1),
    )
    nota = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["martillo"], Decimal("1"), Decimal("10.00"))]
    )

    resultado = entregar_nota_venta(nota, almacen, user_a)

    assert resultado["comision"] is None
    assert ComisionVenta.objects.count() == 0


def test_esquema_inactivo_no_devenga(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor
):
    EsquemaComision.objects.create(
        id_empresa=empresa_a, vendedor=vendedor, porcentaje_base=Decimal("5.0000"), activo=False
    )
    nota = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["martillo"], Decimal("1"), Decimal("10.00"))]
    )

    assert entregar_nota_venta(nota, almacen, user_a)["comision"] is None


def test_esquema_de_otra_empresa_no_aplica(
    empresa_a, empresa_b, cliente, almacen, productos, stock, user_a, vendedor
):
    """R-CODE-1: un esquema del mismo vendedor en la empresa B no comisiona ventas de A."""
    EsquemaComision.objects.create(
        id_empresa=empresa_b, vendedor=vendedor, porcentaje_base=Decimal("50.0000")
    )
    nota = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["martillo"], Decimal("1"), Decimal("10.00"))]
    )

    assert entregar_nota_venta(nota, almacen, user_a)["comision"] is None


def test_gana_el_esquema_con_vigente_desde_mas_reciente(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor
):
    """Dos esquemas vigentes: el de ``vigente_desde`` más reciente decide."""
    EsquemaComision.objects.create(
        id_empresa=empresa_a,
        vendedor=vendedor,
        porcentaje_base=Decimal("5.0000"),
        vigente_desde=timezone.localdate() - timedelta(days=365),
    )
    nuevo = EsquemaComision.objects.create(
        id_empresa=empresa_a,
        vendedor=vendedor,
        porcentaje_base=Decimal("7.0000"),
        vigente_desde=timezone.localdate() - timedelta(days=10),
    )
    nota = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["martillo"], Decimal("1"), Decimal("100.00"))]
    )

    comision = entregar_nota_venta(nota, almacen, user_a)["comision"]

    assert comision.esquema == nuevo
    assert comision.monto == Decimal("7.0000")


def test_devengo_idempotente(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor, esquema_5
):
    """Una segunda invocación devuelve la MISMA comisión (OneToOne), sin duplicar."""
    nota = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["martillo"], Decimal("1"), Decimal("10.00"))]
    )
    primera = entregar_nota_venta(nota, almacen, user_a)["comision"]

    segunda = devengar_comision_venta(nota)

    assert segunda.pk == primera.pk
    assert ComisionVenta.objects.filter(nota_venta=nota).count() == 1


# ── Anulación ─────────────────────────────────────────────────────────────────


def _nota_entregada_con_comision(empresa, cliente, almacen, productos, usuario, vendedor):
    nota = _crear_nota(
        empresa, cliente, vendedor, [(productos["martillo"], Decimal("2"), Decimal("50.00"))]
    )
    comision = entregar_nota_venta(nota, almacen, usuario)["comision"]
    return nota, comision


def test_anular_nota_anula_comision(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor, esquema_5
):
    nota, comision = _nota_entregada_con_comision(
        empresa_a, cliente, almacen, productos, user_a, vendedor
    )

    anulada = anular_comision_de_nota_venta(nota)

    assert anulada.pk == comision.pk
    comision.refresh_from_db()
    assert comision.estado == "ANULADA"


def test_anular_sin_comision_es_noop(
    empresa_a, cliente, almacen, productos, stock, user_a, esquema_5
):
    nota = _crear_nota(
        empresa_a, cliente, None, [(productos["martillo"], Decimal("1"), Decimal("10.00"))]
    )
    entregar_nota_venta(nota, almacen, user_a)

    assert anular_comision_de_nota_venta(nota) is None


def test_anular_comision_liquidada_falla_controlado(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor, esquema_5
):
    nota, comision = _nota_entregada_con_comision(
        empresa_a, cliente, almacen, productos, user_a, vendedor
    )
    comision.estado = "LIQUIDADA"
    comision.fecha_liquidacion = timezone.localdate()
    comision.save(update_fields=["estado", "fecha_liquidacion"])

    with pytest.raises(VentaError, match="liquidada"):
        anular_comision_de_nota_venta(nota)

    comision.refresh_from_db()
    assert comision.estado == "LIQUIDADA"  # nada cambió


# ── Conversión pedido → nota copia el vendedor ────────────────────────────────


def test_convertir_pedido_copia_vendedor(empresa_a, cliente, productos, vendedor):
    from apps.ventas.models import DetallePedido, Pedido
    from apps.ventas.services import convertir_pedido_a_nota_venta

    pedido = Pedido.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        id_vendedor=vendedor,
        numero_pedido="PED-COM-0001",
        fecha_pedido=timezone.localdate(),
        estado="APROBADO",
    )
    DetallePedido.objects.create(
        id_pedido=pedido,
        id_producto=productos["martillo"],
        cantidad=Decimal("1"),
        precio_unitario=Decimal("10.00"),
        subtotal=Decimal("10.00"),
    )

    nota = convertir_pedido_a_nota_venta(pedido, usuario=None)

    assert nota.id_vendedor == vendedor


# ── Liquidación ───────────────────────────────────────────────────────────────


def test_liquidar_comisiones_solo_periodo_y_devengadas(
    empresa_a, cliente, almacen, productos, stock, user_a, vendedor, esquema_5
):
    hoy = timezone.localdate()
    en_rango_1 = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["martillo"], Decimal("1"), Decimal("100.00"))]
    )
    en_rango_2 = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["cable"], Decimal("2"), Decimal("30.00"))]
    )
    fuera_de_rango = _crear_nota(
        empresa_a,
        cliente,
        vendedor,
        [(productos["martillo"], Decimal("1"), Decimal("100.00"))],
        fecha=hoy - timedelta(days=60),
    )
    for nota in (en_rango_1, en_rango_2, fuera_de_rango):
        entregar_nota_venta(nota, almacen, user_a)
    anulada = _crear_nota(
        empresa_a, cliente, vendedor, [(productos["cable"], Decimal("1"), Decimal("10.00"))]
    )
    entregar_nota_venta(anulada, almacen, user_a)
    anular_comision_de_nota_venta(anulada)

    resultado = liquidar_comisiones(
        empresas=[empresa_a],
        vendedor=vendedor,
        desde=hoy - timedelta(days=30),
        hasta=hoy,
        usuario=user_a,
    )

    # 100.00*5% + 60.00*5% = 5.0000 + 3.0000 = 8.0000 (la anulada y la vieja no entran)
    assert resultado["liquidadas"] == 2
    assert resultado["monto_total"] == Decimal("8.0000")
    liquidadas = ComisionVenta.objects.filter(estado="LIQUIDADA")
    assert liquidadas.count() == 2
    assert all(c.fecha_liquidacion == hoy and c.liquidada_por == user_a for c in liquidadas)
    # La de fuera de rango sigue DEVENGADA; la anulada sigue ANULADA
    assert ComisionVenta.objects.filter(estado="DEVENGADA").count() == 1
    assert ComisionVenta.objects.filter(estado="ANULADA").count() == 1

    # Idempotencia natural: segunda corrida del mismo rango → 0
    repeticion = liquidar_comisiones(
        empresas=[empresa_a],
        vendedor=vendedor,
        desde=hoy - timedelta(days=30),
        hasta=hoy,
        usuario=user_a,
    )
    assert repeticion == {"liquidadas": 0, "monto_total": Decimal("0")}


def test_liquidar_rango_invertido_falla(empresa_a, user_a, vendedor):
    with pytest.raises(VentaError, match="inválido"):
        liquidar_comisiones(
            empresas=[empresa_a],
            vendedor=vendedor,
            desde=timezone.localdate(),
            hasta=timezone.localdate() - timedelta(days=1),
            usuario=user_a,
        )
