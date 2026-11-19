"""Endpoint atómico de venta POS offline — ADR-012.

``POST /api/sync/push/ventas/`` crea nota + detalles + entrega + pagos como una
sola unidad atómica e idempotente. Estos tests cubren la batería exigida por el
ADR antes de mergear código de dinero: happy path, replay (outbox), totales
incoherentes, falta de clave, aislamiento multi-tenant y rollback completo.
"""

from decimal import Decimal
from itertools import count

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db

URL = "/api/sync/push/ventas/"
_SEQ = count(1)


def _producto_con_stock(empresa, usuario, *, precio="20.00", stock="100"):
    from apps.almacenes.models import Almacen
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
    from apps.inventario.services import registrar_movimiento

    n = next(_SEQ)
    almacen = Almacen.objects.create(
        id_empresa=empresa, nombre_almacen=f"Almacén POS {n}", codigo_almacen=f"ALM-POS-{n}"
    )
    unidad = UnidadMedida.objects.create(id_empresa=empresa, nombre="Unidad", abreviatura=f"UNP-{n}", tipo="CANTIDAD")
    categoria = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria=f"Cat POS {n}")
    producto = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto=f"Producto POS {n}",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=empresa.id_moneda_base,
        precio_venta_sugerido=Decimal(precio),
    )
    registrar_movimiento(
        empresa=empresa,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto,
        cantidad=Decimal(stock),
        almacen_destino=almacen,
        usuario=usuario,
    )
    return producto, almacen


def _cliente(empresa, rif="V-12345678-9"):
    from apps.crm.models import Cliente

    return Cliente.objects.create(id_empresa=empresa, razon_social="Consumidor POS", rif=rif)


def _caja_virtual(empresa, moneda):
    from apps.finanzas.models import Caja

    return Caja.objects.create(empresa=empresa, nombre="Caja POS", moneda=moneda, saldo_actual=Decimal("0"))


def _sobre(
    cliente,
    almacen,
    producto,
    metodo,
    moneda,
    *,
    caja=None,
    cantidad="2",
    precio="20.00",
    client_uuid="venta-pos-uuid-1",
    total="40.00",
):
    pago = {"id_metodo_pago": str(metodo.id_metodo_pago), "id_moneda": str(moneda.id_moneda), "monto": total}
    if caja is not None:
        pago["id_caja_virtual"] = str(caja.id_caja)
    return {
        "client_uuid": client_uuid,
        "fecha_local": "2026-06-19T10:00:00-04:00",
        "id_cliente": str(cliente.id_cliente),
        "id_almacen": str(almacen.id_almacen),
        "detalles": [{"id_producto": str(producto.id_producto), "cantidad": cantidad, "precio_unitario": precio}],
        "pagos": [pago],
        "totales_cliente": {"total": total},
    }


def _hdr(clave="venta-pos-uuid-1"):
    return {"HTTP_IDEMPOTENCY_KEY": clave}


def _count_notas(empresa):
    from apps.ventas.models import NotaVenta

    return NotaVenta.objects.filter(id_empresa=empresa).count()


def test_happy_path_crea_nota_entregada_con_pago(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    caja = _caja_virtual(empresa_a, moneda_usd)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, caja=caja)

    r = client_a.post(URL, sobre, format="json", **_hdr())

    assert r.status_code == 201, r.data
    assert r.data["estado"] == "ENTREGADA"
    assert r.data["total"] == "40.0000"
    assert r.data["movimientos"] == 1
    assert len(r.data["pagos"]) == 1
    assert _count_notas(empresa_a) == 1

    # El pago afectó el saldo de la caja (efectos financieros aplicados).
    caja.refresh_from_db()
    assert caja.saldo_actual == Decimal("40.00")

    # El servidor recalcula el subtotal de la línea (no confía en el cliente).
    from apps.ventas.models import DetalleNotaVenta

    detalle = DetalleNotaVenta.objects.get(id_nota_venta=r.data["id_nota_venta"])
    assert detalle.subtotal == Decimal("40.0000")


def test_replay_misma_clave_no_duplica(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    caja = _caja_virtual(empresa_a, moneda_usd)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, caja=caja)

    r1 = client_a.post(URL, sobre, format="json", **_hdr())
    r2 = client_a.post(URL, sobre, format="json", **_hdr())

    assert r1.status_code == 201, r1.data
    assert r2.status_code == 201, r2.data
    assert r1.data["id_nota_venta"] == r2.data["id_nota_venta"]
    assert _count_notas(empresa_a) == 1

    # El stock se despachó UNA sola vez (no doble descuento por el replay).
    caja.refresh_from_db()
    assert caja.saldo_actual == Decimal("40.00")
    from apps.finanzas.models import Pago

    assert Pago.objects.filter(id_empresa=empresa_a).count() == 1


def test_total_incoherente_rechaza_y_revierte(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, total="40.00")
    sobre["totales_cliente"]["total"] = "999.00"  # difiere del cálculo del servidor

    r = client_a.post(URL, sobre, format="json", **_hdr())

    assert r.status_code == 422, r.data
    assert "total" in r.data["error"].lower()
    assert _count_notas(empresa_a) == 0  # rollback completo: ni la nota queda


def test_sin_idempotency_key_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd)

    r = client_a.post(URL, sobre, format="json")  # sin cabecera

    assert r.status_code == 400, r.data
    assert "Idempotency-Key" in r.data["error"]
    assert _count_notas(empresa_a) == 0


def test_aislamiento_multitenant_producto_ajeno(
    client_a, empresa_a, empresa_b, user_a, user_b, moneda_usd, metodo_efectivo
):
    # Recursos de A, pero el producto es de la empresa B (intento de IDOR).
    _, almacen = _producto_con_stock(empresa_a, user_a)
    producto_b, _ = _producto_con_stock(empresa_b, user_b)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto_b, metodo_efectivo, moneda_usd)

    r = client_a.post(URL, sobre, format="json", **_hdr())

    assert r.status_code == 422, r.data
    assert "no encontrado en esta empresa" in r.data["error"]
    assert _count_notas(empresa_a) == 0


def test_pago_invalido_revierte_toda_la_venta(client_a, empresa_a, user_a, moneda_usd):
    """Un método de pago inexistente debe revertir la nota ya creada (atomicidad)."""
    import uuid

    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = {
        "client_uuid": "venta-pos-rollback",
        "id_cliente": str(cliente.id_cliente),
        "id_almacen": str(almacen.id_almacen),
        "detalles": [{"id_producto": str(producto.id_producto), "cantidad": "1", "precio_unitario": "10.00"}],
        "pagos": [{"id_metodo_pago": str(uuid.uuid4()), "id_moneda": str(moneda_usd.id_moneda), "monto": "10.00"}],
        "totales_cliente": {"total": "10.00"},
    }

    r = client_a.post(URL, sobre, format="json", **_hdr("venta-pos-rollback"))

    assert r.status_code == 422, r.data
    assert _count_notas(empresa_a) == 0  # la nota creada antes del pago se revirtió


def test_detalles_vacios_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    _, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = {
        "client_uuid": "venta-sin-detalles",
        "id_cliente": str(cliente.id_cliente),
        "id_almacen": str(almacen.id_almacen),
        "detalles": [],
        "pagos": [],
    }
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-sin-detalles"))
    assert r.status_code == 422, r.data
    assert "detalles" in r.data["error"].lower()


def test_cliente_ajeno_rechaza(client_a, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente_b = _cliente(empresa_b, rif="V-99999999-9")
    sobre = _sobre(cliente_b, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-cli-ajeno")
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-cli-ajeno"))
    assert r.status_code == 422, r.data
    assert "id_cliente" in r.data["error"]
    assert _count_notas(empresa_a) == 0


def test_caja_virtual_ajena_rechaza(client_a, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    caja_b = _caja_virtual(empresa_b, moneda_usd)
    sobre = _sobre(
        cliente, almacen, producto, metodo_efectivo, moneda_usd, caja=caja_b, client_uuid="venta-caja-ajena"
    )
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-caja-ajena"))
    assert r.status_code == 422, r.data
    assert "id_caja_virtual" in r.data["error"]
    assert _count_notas(empresa_a) == 0  # rollback: la nota no queda


def test_moneda_inexistente_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    import uuid

    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-moneda-mala")
    sobre["pagos"][0]["id_moneda"] = str(uuid.uuid4())
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-moneda-mala"))
    assert r.status_code == 422, r.data
    assert _count_notas(empresa_a) == 0


def test_cantidad_invalida_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(
        cliente, almacen, producto, metodo_efectivo, moneda_usd, cantidad="0", client_uuid="venta-cant-cero"
    )
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-cant-cero"))
    assert r.status_code == 422, r.data
    assert "cantidad" in r.data["error"].lower()
    assert _count_notas(empresa_a) == 0


def test_cuerpo_no_objeto_rechaza(client_a, empresa_a, user_a):
    r = client_a.post(URL, [], format="json", **_hdr("venta-lista"))
    assert r.status_code == 422, r.data
    assert "objeto JSON" in r.data["error"]


def test_pagos_no_es_lista_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-pagos-nolista")
    sobre["pagos"] = "no-soy-lista"
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-pagos-nolista"))
    assert r.status_code == 422, r.data
    assert "pagos" in r.data["error"].lower()


def test_falta_id_cliente_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-sin-cliente")
    sobre.pop("id_cliente")
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-sin-cliente"))
    assert r.status_code == 422, r.data
    assert "id_cliente" in r.data["error"]


def test_sin_client_uuid_ni_numero_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd)
    sobre.pop("client_uuid")  # sin client_uuid ni numero_nota → no se puede numerar
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-sin-uuid"))
    assert r.status_code == 422, r.data
    assert "numero_nota" in r.data["error"]


def test_detalle_no_objeto_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-det-nodict")
    sobre["detalles"] = ["no-soy-objeto"]
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-det-nodict"))
    assert r.status_code == 422, r.data


def test_precio_negativo_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(
        cliente, almacen, producto, metodo_efectivo, moneda_usd, precio="-5.00", client_uuid="venta-precio-neg"
    )
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-precio-neg"))
    assert r.status_code == 422, r.data
    assert "precio" in r.data["error"].lower()


def test_pago_no_objeto_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-pago-nodict")
    sobre["pagos"] = ["no-soy-objeto"]
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-pago-nodict"))
    assert r.status_code == 422, r.data


def test_pago_sin_metodo_rechaza(client_a, empresa_a, user_a, moneda_usd):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = {
        "client_uuid": "venta-sin-metodo",
        "id_cliente": str(cliente.id_cliente),
        "id_almacen": str(almacen.id_almacen),
        "detalles": [{"id_producto": str(producto.id_producto), "cantidad": "1", "precio_unitario": "5.00"}],
        "pagos": [{"id_moneda": str(moneda_usd.id_moneda), "monto": "5.00"}],
    }
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-sin-metodo"))
    assert r.status_code == 422, r.data
    assert "id_metodo_pago" in r.data["error"]


def test_pago_monto_invalido_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-monto-abc")
    sobre["pagos"][0]["monto"] = "abc"
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-monto-abc"))
    assert r.status_code == 422, r.data


def test_pago_monto_cero_rechaza(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-monto-cero")
    sobre["pagos"][0]["monto"] = "0"
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-monto-cero"))
    assert r.status_code == 422, r.data
    assert "monto" in r.data["error"].lower()


def test_cuenta_bancaria_ajena_rechaza(client_a, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo):
    import uuid

    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-cuenta-ajena")
    sobre["pagos"][0]["id_cuenta_bancaria"] = str(uuid.uuid4())  # inexistente para esta empresa
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-cuenta-ajena"))
    assert r.status_code == 422, r.data
    assert "id_cuenta_bancaria" in r.data["error"]
    assert _count_notas(empresa_a) == 0


def test_sin_totales_cliente_se_acepta(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    """`totales_cliente` es opcional (verificación defensiva); sin él la venta procede."""
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente = _cliente(empresa_a)
    caja = _caja_virtual(empresa_a, moneda_usd)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, caja=caja, client_uuid="venta-sin-totales")
    sobre.pop("totales_cliente")
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-sin-totales"))
    assert r.status_code == 201, r.data
    assert r.data["estado"] == "ENTREGADA"
    assert r.data["alerta_stock_negativo"] is False
    assert r.data["productos_stock_negativo"] == []


# ── Stock negativo POS + REQUIERE_REVISION + resolución por sucursal ─────────


def _param_stock_negativo(empresa, valor="true", *, activo=True):
    from apps.configuracion_motor.models import ParametroSistema

    return ParametroSistema.objects.create(
        id_empresa=empresa,
        nombre_parametro="Permitir stock negativo POS",
        codigo_parametro="permitir_stock_negativo_pos",
        valor_parametro=valor,
        tipo_dato="BOOLEANO",
        activo=activo,
    )


def test_stock_insuficiente_sin_parametro_rechaza_422_y_revierte(
    client_a, empresa_a, user_a, moneda_usd, metodo_efectivo
):
    from apps.finanzas.models import Pago
    from apps.inventario.models import MovimientoInventario, StockActual

    producto, almacen = _producto_con_stock(empresa_a, user_a, stock="1")
    cliente = _cliente(empresa_a)
    caja = _caja_virtual(empresa_a, moneda_usd)
    sobre = _sobre(
        cliente,
        almacen,
        producto,
        metodo_efectivo,
        moneda_usd,
        caja=caja,
        cantidad="3",
        total="60.00",
        client_uuid="venta-stock-insuf-default",
    )

    r = client_a.post(URL, sobre, format="json", **_hdr("venta-stock-insuf-default"))

    assert r.status_code == 422, r.data
    assert r.data["codigo"] == "REQUIERE_REVISION"
    assert "stock insuficiente" in r.data["error"].lower()
    assert _count_notas(empresa_a) == 0
    assert Pago.objects.filter(id_empresa=empresa_a).count() == 0
    assert MovimientoInventario.objects.filter(id_empresa=empresa_a, tipo_movimiento="DESPACHO_VENTA").count() == 0
    stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen)
    assert stock.cantidad_disponible == Decimal("1.0000")


def test_stock_insuficiente_con_parametro_false_rechaza_422(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    _param_stock_negativo(empresa_a, "false")
    producto, almacen = _producto_con_stock(empresa_a, user_a, stock="1")
    cliente = _cliente(empresa_a)
    sobre = _sobre(
        cliente,
        almacen,
        producto,
        metodo_efectivo,
        moneda_usd,
        cantidad="2",
        total="40.00",
        client_uuid="venta-stock-false",
    )

    r = client_a.post(URL, sobre, format="json", **_hdr("venta-stock-false"))

    assert r.status_code == 422, r.data
    assert r.data["codigo"] == "REQUIERE_REVISION"
    assert _count_notas(empresa_a) == 0


def test_stock_negativo_permitido_crea_venta_con_alerta_y_aisla_tenant(
    client_a, client_b, empresa_a, empresa_b, user_a, user_b, moneda_usd, metodo_efectivo
):
    from apps.inventario.models import StockActual

    _param_stock_negativo(empresa_a, "true")
    producto_a, almacen_a = _producto_con_stock(empresa_a, user_a, stock="1")
    cliente_a = _cliente(empresa_a)
    caja_a = _caja_virtual(empresa_a, moneda_usd)
    sobre_a = _sobre(
        cliente_a,
        almacen_a,
        producto_a,
        metodo_efectivo,
        moneda_usd,
        caja=caja_a,
        cantidad="4",
        total="80.00",
        client_uuid="venta-stock-neg-ok",
    )

    r1 = client_a.post(URL, sobre_a, format="json", **_hdr("venta-stock-neg-ok"))
    r2 = client_a.post(URL, sobre_a, format="json", **_hdr("venta-stock-neg-ok"))

    assert r1.status_code == 201, r1.data
    assert r1.data["alerta_stock_negativo"] is True
    assert len(r1.data["productos_stock_negativo"]) == 1
    assert r1.data["productos_stock_negativo"][0]["id_producto"] == str(producto_a.id_producto)
    assert Decimal(r1.data["productos_stock_negativo"][0]["cantidad_disponible"]) == Decimal("-3.0000")

    # Idempotencia conservada: replay devuelve el mismo 201 sin volver a descontar.
    assert r2.status_code == 201
    assert r2.data["id_nota_venta"] == r1.data["id_nota_venta"]
    stock_a = StockActual.objects.get(id_producto=producto_a, id_almacen=almacen_a)
    assert stock_a.cantidad_disponible == Decimal("-3.0000")

    # Multi-tenant: empresa_b sin el parámetro sigue rechazada con 422 REQUIERE_REVISION.
    producto_b, almacen_b = _producto_con_stock(empresa_b, user_b, stock="1")
    cliente_b = _cliente(empresa_b, rif="V-88888888-8")
    sobre_b = _sobre(
        cliente_b,
        almacen_b,
        producto_b,
        metodo_efectivo,
        moneda_usd,
        cantidad="4",
        total="80.00",
        client_uuid="venta-stock-neg-b",
    )
    rb = client_b.post(URL, sobre_b, format="json", **_hdr("venta-stock-neg-b"))
    assert rb.status_code == 422, rb.data
    assert rb.data["codigo"] == "REQUIERE_REVISION"
    assert _count_notas(empresa_b) == 0


def test_stock_negativo_parametro_global_y_override_tenant(
    client_a, client_b, empresa_a, empresa_b, user_a, user_b, moneda_usd, metodo_efectivo
):
    from apps.configuracion_motor.models import ParametroSistema

    # Global truthy ("si") aplica a empresa_a; empresa_b tiene override explícito "false".
    ParametroSistema.objects.create(
        id_empresa=None,
        nombre_parametro="Global stock negativo POS",
        codigo_parametro="permitir_stock_negativo_pos",
        valor_parametro="si",
        tipo_dato="BOOLEANO",
        activo=True,
    )
    _param_stock_negativo(empresa_b, "false")

    producto_a, almacen_a = _producto_con_stock(empresa_a, user_a, stock="1")
    cliente_a = _cliente(empresa_a)
    sobre_a = _sobre(
        cliente_a,
        almacen_a,
        producto_a,
        metodo_efectivo,
        moneda_usd,
        cantidad="2",
        total="40.00",
        client_uuid="venta-global-true",
    )
    ra = client_a.post(URL, sobre_a, format="json", **_hdr("venta-global-true"))
    assert ra.status_code == 201, ra.data
    assert ra.data["alerta_stock_negativo"] is True

    producto_b, almacen_b = _producto_con_stock(empresa_b, user_b, stock="1")
    cliente_b = _cliente(empresa_b, rif="V-77777777-7")
    sobre_b = _sobre(
        cliente_b,
        almacen_b,
        producto_b,
        metodo_efectivo,
        moneda_usd,
        cantidad="2",
        total="40.00",
        client_uuid="venta-override-false",
    )
    rb = client_b.post(URL, sobre_b, format="json", **_hdr("venta-override-false"))
    assert rb.status_code == 422, rb.data
    assert rb.data["codigo"] == "REQUIERE_REVISION"


def test_resuelve_almacen_por_id_sucursal_y_falla_si_no_hay_almacen(
    client_a, empresa_a, user_a, moneda_usd, metodo_efectivo
):
    from apps.core.models import Sucursal
    from apps.finanzas.models import CajaFisica

    sucursal = Sucursal.objects.create(id_empresa=empresa_a, nombre="Sucursal POS", codigo_sucursal="SUC-POS-1")
    producto, almacen = _producto_con_stock(empresa_a, user_a, stock="10")
    almacen.id_sucursal = sucursal
    almacen.save(update_fields=["id_sucursal"])
    cliente = _cliente(empresa_a)
    caja_fisica = CajaFisica.objects.create(
        empresa=empresa_a, sucursal=sucursal, nombre="Caja Sucursal", identificador_dispositivo="POS-SUC-1"
    )

    sobre = _sobre(
        cliente,
        almacen,
        producto,
        metodo_efectivo,
        moneda_usd,
        cantidad="2",
        total="40.00",
        client_uuid="venta-por-sucursal",
    )
    sobre.pop("id_almacen")
    sobre["id_sucursal"] = str(sucursal.id_sucursal)
    sobre["id_caja"] = str(caja_fisica.id_caja_fisica)

    r = client_a.post(URL, sobre, format="json", **_hdr("venta-por-sucursal"))
    assert r.status_code == 201, r.data
    assert r.data["movimientos"] == 1
    from apps.finanzas.models import Pago

    pago = Pago.objects.get(pk=r.data["pagos"][0])
    assert pago.id_caja_fisica_id == caja_fisica.id_caja_fisica

    # Sucursal sin almacén asociado ni almacén sin sucursal → 422 REQUIERE_REVISION.
    sucursal_vacia = Sucursal.objects.create(id_empresa=empresa_a, nombre="Sucursal Vacia", codigo_sucursal="SUC-VAC")
    sobre_vacia = _sobre(
        cliente,
        almacen,
        producto,
        metodo_efectivo,
        moneda_usd,
        cantidad="1",
        total="20.00",
        client_uuid="venta-suc-sin-alm",
    )
    sobre_vacia.pop("id_almacen")
    sobre_vacia["id_sucursal"] = str(sucursal_vacia.id_sucursal)
    r_vacia = client_a.post(URL, sobre_vacia, format="json", **_hdr("venta-suc-sin-alm"))
    assert r_vacia.status_code == 422, r_vacia.data
    assert r_vacia.data["codigo"] == "REQUIERE_REVISION"
    assert "id_almacen" in r_vacia.data["error"]


def test_total_incoherente_y_recursos_invalidos_devuelven_codigo_requiere_revision(
    client_a, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo
):
    from apps.finanzas.models import CajaFisica

    producto, almacen = _producto_con_stock(empresa_a, user_a, stock="10")
    cliente = _cliente(empresa_a)
    sobre = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-rev-total")
    sobre["totales_cliente"]["total"] = "99.00"
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-rev-total"))
    assert r.status_code == 422
    assert r.data["codigo"] == "REQUIERE_REVISION"

    # Sin id_almacen ni id_sucursal
    sobre_sin_alm = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-sin-alm")
    sobre_sin_alm.pop("id_almacen")
    r_alm = client_a.post(URL, sobre_sin_alm, format="json", **_hdr("venta-sin-alm"))
    assert r_alm.status_code == 422
    assert r_alm.data["codigo"] == "REQUIERE_REVISION"

    # id_caja de empresa ajena → 422 REQUIERE_REVISION
    caja_b = CajaFisica.objects.create(empresa=empresa_b, nombre="Caja B", identificador_dispositivo="POS-B")
    sobre_caja_b = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-caja-fis-b")
    sobre_caja_b["id_caja"] = str(caja_b.id_caja_fisica)
    r_cb = client_a.post(URL, sobre_caja_b, format="json", **_hdr("venta-caja-fis-b"))
    assert r_cb.status_code == 422
    assert r_cb.data["codigo"] == "REQUIERE_REVISION"


def test_descuento_y_tasa_cambio_faltante_en_pago(client_a, empresa_a, user_a, moneda_usd, metodo_efectivo):
    from tests.factories import MonedaFactory

    producto, almacen = _producto_con_stock(empresa_a, user_a, stock="10", precio="20.00")
    cliente = _cliente(empresa_a)
    caja = _caja_virtual(empresa_a, moneda_usd)

    # Descuento 10% sobre 2 × 20.00 = 36.00
    sobre = _sobre(
        cliente,
        almacen,
        producto,
        metodo_efectivo,
        moneda_usd,
        caja=caja,
        cantidad="2",
        precio="20.00",
        total="36.00",
        client_uuid="venta-con-descuento",
    )
    sobre["detalles"][0]["descuento_porcentaje"] = "10"
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-con-descuento"))
    assert r.status_code == 201, r.data
    assert r.data["total"] == "36.0000"

    # Pago en otra moneda sin TasaCambio → 422 REQUIERE_REVISION y rollback
    moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
    sobre_sin_tasa = _sobre(
        cliente,
        almacen,
        producto,
        metodo_efectivo,
        moneda_ves,
        cantidad="1",
        precio="20.00",
        total="20.00",
        client_uuid="venta-sin-tasa",
    )
    r_tasa = client_a.post(URL, sobre_sin_tasa, format="json", **_hdr("venta-sin-tasa"))
    assert r_tasa.status_code == 422, r_tasa.data
    assert r_tasa.data["codigo"] == "REQUIERE_REVISION"
    assert _count_notas(empresa_a) == 1  # solo la venta con descuento quedó


def test_descuento_invalido_y_caja_fisica_en_pago(client_a, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo):
    from apps.finanzas.models import CajaFisica, Pago

    producto, almacen = _producto_con_stock(empresa_a, user_a, stock="10", precio="10.00")
    cliente = _cliente(empresa_a)
    caja_a = CajaFisica.objects.create(empresa=empresa_a, nombre="Caja A", identificador_dispositivo="POS-A")
    caja_b = CajaFisica.objects.create(empresa=empresa_b, nombre="Caja B", identificador_dispositivo="POS-B")

    # Descuento > 100 → 422
    sobre_desc = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-desc-mal")
    sobre_desc["detalles"][0]["descuento_porcentaje"] = "150"
    r_desc = client_a.post(URL, sobre_desc, format="json", **_hdr("venta-desc-mal"))
    assert r_desc.status_code == 422

    # id_caja_fisica ajena en pagos[] → 422 y rollback
    sobre_cf_b = _sobre(cliente, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-cf-ajena")
    sobre_cf_b["pagos"][0]["id_caja_fisica"] = str(caja_b.id_caja_fisica)
    r_cfb = client_a.post(URL, sobre_cf_b, format="json", **_hdr("venta-cf-ajena"))
    assert r_cfb.status_code == 422

    # id_caja_fisica propia en pagos[] y id_caja no-UUID en sobre → 201 OK
    sobre_ok = _sobre(
        cliente,
        almacen,
        producto,
        metodo_efectivo,
        moneda_usd,
        cantidad="1",
        precio="10.00",
        total="10.00",
        client_uuid="venta-cf-ok",
    )
    sobre_ok["id_caja"] = "no-es-uuid"
    sobre_ok["pagos"][0]["id_caja_fisica"] = str(caja_a.id_caja_fisica)
    r_ok = client_a.post(URL, sobre_ok, format="json", **_hdr("venta-cf-ok"))
    assert r_ok.status_code == 201, r_ok.data
    assert Pago.objects.get(pk=r_ok.data["pagos"][0]).id_caja_fisica_id == caja_a.id_caja_fisica
