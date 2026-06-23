"""
Tests del stepper de operaciones de inventario (recepción / entrega).

Cubre la maquinaria de pasos configurables y la integración con stock,
valoración y contabilidad:
  T03  Recepción → confirmar pasos en orden → stock sube → asiento DR Inv / CR CxP.
  T04  Entrega de venta → stock baja → asientos COGS + ingresos.
  T05  Entrega por transferencia interna → stock se mueve entre almacenes.
  T12  Confirmar el paso 2 antes del 1 → HTTP 400.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.almacenes.models import Almacen
from apps.contabilidad.models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas
from apps.inventario.models import (
    CategoriaProducto,
    OperacionInventario,
    PasoOperacion,
    Producto,
    StockActual,
    UnidadMedida,
)
from apps.inventario.services import registrar_movimiento

pytestmark = pytest.mark.django_db

REC = "/api/inventario/recepciones/"
ENT = "/api/inventario/entregas/"


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def almacen(empresa_a):
    return Almacen.objects.create(id_empresa=empresa_a, nombre_almacen="Central", codigo_almacen="ALM-OP")


@pytest.fixture
def almacen_dest(empresa_a):
    return Almacen.objects.create(id_empresa=empresa_a, nombre_almacen="Sucursal", codigo_almacen="ALM-OP2")


@pytest.fixture
def producto(empresa_a, moneda_usd):
    unidad = UnidadMedida.objects.create(id_empresa=empresa_a, nombre="U", abreviatura="U-OP", tipo="CANTIDAD")
    cat = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat OP")
    return Producto.objects.create(
        id_empresa=empresa_a, id_categoria=cat, id_unidad_medida_base=unidad,
        id_moneda_precio=moneda_usd, nombre_producto="Prod OP", metodo_valoracion="PROMEDIO",
    )


def _pasos(empresa, almacen, tipo, nombres):
    for i, nombre in enumerate(nombres, start=1):
        PasoOperacion.objects.create(
            id_empresa=empresa, id_almacen=almacen, tipo_operacion=tipo,
            nombre_paso=nombre, secuencia=i,
        )


def _cuenta(empresa, codigo, nombre, tipo="ACTIVO", nat="DEUDORA"):
    return PlanCuentas.objects.create(
        id_empresa=empresa, codigo_cuenta=codigo, nombre_cuenta=nombre,
        tipo_cuenta=tipo, naturaleza=nat, nivel=1,
    )


def _mapeo(empresa, tipo, debe, haber):
    return MapeoContable.objects.create(
        id_empresa=empresa, tipo_asiento=tipo, cuenta_debe=debe, cuenta_haber=haber, activo=True,
    )


def _confirmar_todos_en_orden(client, base, op_id, pasos):
    """Confirma cada paso en orden de secuencia vía API. Devuelve la última respuesta."""
    resp = None
    for paso in sorted(pasos, key=lambda p: p["secuencia"]):
        resp = client.post(f"{base}{op_id}/step/{paso['id_operacion_paso']}/confirm/")
        assert resp.status_code == 200, resp.content
    return resp


# ── T03 — Recepción ───────────────────────────────────────────────────────────


def test_recepcion_sube_stock_y_genera_asiento(client_a, empresa_a, almacen, producto):
    _pasos(empresa_a, almacen, "RECEPCION", ["Confirmación", "Calidad", "Ubicación"])
    inv = _cuenta(empresa_a, "1.1.05", "Inventario")
    cxp = _cuenta(empresa_a, "2.1.01", "CxP", tipo="PASIVO", nat="ACREEDORA")
    _mapeo(empresa_a, "RECEPCION_MERCANCIA", inv, cxp)

    payload = {
        "almacen": str(almacen.id_almacen), "origen_tipo": "PURCHASE",
        "lineas": [{"producto": str(producto.id_producto), "cantidad": "10", "costo_unitario": "7.00"}],
    }
    resp = client_a.post(REC, payload, format="json")
    assert resp.status_code == 201, resp.content
    op = resp.json()
    assert op["estado"] == "EN_PROCESO"
    assert len(op["pasos"]) == 3

    _confirmar_todos_en_orden(client_a, REC, op["id_operacion"], op["pasos"])

    OperacionInventario.objects.get(id_operacion=op["id_operacion"]).refresh_from_db()
    assert OperacionInventario.objects.get(id_operacion=op["id_operacion"]).estado == "COMPLETADA"
    stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen)
    assert stock.cantidad_disponible == Decimal("10.0000")

    asiento = AsientoContable.objects.get(
        id_documento_origen=op["id_operacion"], nombre_modelo_origen="OperacionInventario"
    )
    detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
    debe = next(d for d in detalles if d.debe > 0)
    haber = next(d for d in detalles if d.haber > 0)
    assert debe.id_cuenta_contable_id == inv.pk   # DR Inventario
    assert haber.id_cuenta_contable_id == cxp.pk    # CR CxP
    assert debe.debe == Decimal("70.00")            # 10 × 7.00
    assert debe.debe == haber.haber


# ── T12 — Orden de pasos ──────────────────────────────────────────────────────


def test_confirmar_paso_fuera_de_orden_devuelve_400(client_a, empresa_a, almacen, producto):
    _pasos(empresa_a, almacen, "RECEPCION", ["Confirmación", "Calidad"])
    payload = {
        "almacen": str(almacen.id_almacen), "origen_tipo": "PURCHASE",
        "lineas": [{"producto": str(producto.id_producto), "cantidad": "5", "costo_unitario": "3.00"}],
    }
    op = client_a.post(REC, payload, format="json").json()
    paso2 = next(p for p in op["pasos"] if p["secuencia"] == 2)

    resp = client_a.post(f"{REC}{op['id_operacion']}/step/{paso2['id_operacion_paso']}/confirm/")
    assert resp.status_code == 400
    # No se movió stock ni se completó.
    assert not StockActual.objects.filter(id_producto=producto, id_almacen=almacen).exists()
    assert OperacionInventario.objects.get(id_operacion=op["id_operacion"]).estado == "EN_PROCESO"


# ── T05 — Transferencia interna ───────────────────────────────────────────────


def test_entrega_transferencia_mueve_stock_entre_almacenes(
    client_a, empresa_a, almacen, almacen_dest, producto, user_a
):
    registrar_movimiento(
        empresa=empresa_a, fecha_hora_movimiento=timezone.now(), tipo_movimiento="ENTRADA",
        producto=producto, cantidad=Decimal("20"), almacen_destino=almacen,
        costo_unitario=Decimal("5.00"), usuario=user_a,
    )
    _pasos(empresa_a, almacen, "ENTREGA", ["Picking", "Despacho"])

    payload = {
        "almacen": str(almacen.id_almacen), "origen_tipo": "TRANSFER",
        "almacen_contraparte": str(almacen_dest.id_almacen),
        "lineas": [{"producto": str(producto.id_producto), "cantidad": "8"}],
    }
    op = client_a.post(ENT, payload, format="json").json()
    assert op["pasos"], op
    _confirmar_todos_en_orden(client_a, ENT, op["id_operacion"], op["pasos"])

    assert StockActual.objects.get(id_producto=producto, id_almacen=almacen).cantidad_disponible == Decimal("12.0000")
    assert StockActual.objects.get(id_producto=producto, id_almacen=almacen_dest).cantidad_disponible == Decimal("8.0000")


# ── T04 — Entrega de venta (COGS + ingresos) ──────────────────────────────────


def test_entrega_venta_genera_cogs_e_ingresos(client_a, empresa_a, almacen, producto, user_a):
    from apps.crm.models import Cliente
    from apps.ventas.models import DetalleNotaVenta, NotaVenta

    registrar_movimiento(
        empresa=empresa_a, fecha_hora_movimiento=timezone.now(), tipo_movimiento="ENTRADA",
        producto=producto, cantidad=Decimal("10"), almacen_destino=almacen,
        costo_unitario=Decimal("6.00"), usuario=user_a,
    )
    _pasos(empresa_a, almacen, "ENTREGA", ["Picking", "Empaque", "Despacho"])

    # Mapeos COGS e ingresos.
    costo = _cuenta(empresa_a, "5.1.01", "Costo de Ventas", tipo="GASTO")
    inv = _cuenta(empresa_a, "1.1.05", "Inventario")
    cxc = _cuenta(empresa_a, "1.1.02", "CxC")
    ingresos = _cuenta(empresa_a, "4.1.01", "Ingresos", tipo="INGRESO", nat="ACREEDORA")
    _mapeo(empresa_a, "COSTO_VENTA", costo, inv)
    _mapeo(empresa_a, "NOTA_VENTA", cxc, ingresos)

    cliente = Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente", rif="V-1-0", tipo_cliente="CONTADO"
    )
    nota = NotaVenta.objects.create(
        id_empresa=empresa_a, id_cliente=cliente, numero_nota="NV-OP-1",
        fecha_nota=timezone.now().date(), estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota, id_producto=producto, cantidad=Decimal("4"),
        precio_unitario=Decimal("15.00"), subtotal=Decimal("60.00"),
    )

    payload = {
        "almacen": str(almacen.id_almacen), "origen_tipo": "SALE",
        "origen_id": str(nota.id_nota_venta),
        "lineas": [{"producto": str(producto.id_producto), "cantidad": "4"}],
    }
    op = client_a.post(ENT, payload, format="json").json()
    assert op.get("pasos"), op
    _confirmar_todos_en_orden(client_a, ENT, op["id_operacion"], op["pasos"])

    # Stock bajó 4 (de 10 a 6).
    assert StockActual.objects.get(id_producto=producto, id_almacen=almacen).cantidad_disponible == Decimal("6.0000")

    # COGS: DR Costo de Ventas / CR Inventario == 24 (4 × 6.00).
    cogs = AsientoContable.objects.get(nombre_modelo_origen="MovimientoInventario", id_empresa=empresa_a)
    dcogs = DetalleAsiento.objects.filter(id_asiento=cogs)
    assert next(d for d in dcogs if d.debe > 0).id_cuenta_contable_id == costo.pk
    assert next(d for d in dcogs if d.debe > 0).debe == Decimal("24.00")

    # Ingresos: DR CxC / CR Ingresos == 60 (subtotal de la nota).
    rev = AsientoContable.objects.get(nombre_modelo_origen="NotaVenta", id_empresa=empresa_a)
    drev = DetalleAsiento.objects.filter(id_asiento=rev)
    assert next(d for d in drev if d.haber > 0).id_cuenta_contable_id == ingresos.pk
    assert next(d for d in drev if d.haber > 0).haber == Decimal("60.00")


# ── Aislamiento multi-tenant ──────────────────────────────────────────────────


def test_aislamiento_tenant_operaciones(client_b, empresa_a, almacen, producto):
    _pasos(empresa_a, almacen, "RECEPCION", ["Confirmación"])
    OperacionInventario.objects.create(
        id_empresa=empresa_a, numero="REC-000001", tipo_operacion="RECEPCION",
        origen_tipo="PURCHASE", id_almacen=almacen, fecha=timezone.now(),
    )
    resp = client_b.get(REC)
    assert resp.status_code == 200
    data = resp.json()
    items = data["results"] if isinstance(data, dict) and "results" in data else data
    assert items == []
