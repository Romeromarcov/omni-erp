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
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa, nombre="Unidad", abreviatura=f"UNP-{n}", tipo="CANTIDAD"
    )
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


def _sobre(cliente, almacen, producto, metodo, moneda, *, caja=None, cantidad="2", precio="20.00",
           client_uuid="venta-pos-uuid-1", total="40.00"):
    pago = {"id_metodo_pago": str(metodo.id_metodo_pago), "id_moneda": str(moneda.id_moneda), "monto": total}
    if caja is not None:
        pago["id_caja_virtual"] = str(caja.id_caja)
    return {
        "client_uuid": client_uuid,
        "fecha_local": "2026-06-19T10:00:00-04:00",
        "id_cliente": str(cliente.id_cliente),
        "id_almacen": str(almacen.id_almacen),
        "detalles": [
            {"id_producto": str(producto.id_producto), "cantidad": cantidad, "precio_unitario": precio}
        ],
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
        "detalles": [
            {"id_producto": str(producto.id_producto), "cantidad": "1", "precio_unitario": "10.00"}
        ],
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


def test_cliente_ajeno_rechaza(
    client_a, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo
):
    producto, almacen = _producto_con_stock(empresa_a, user_a)
    cliente_b = _cliente(empresa_b, rif="V-99999999-9")
    sobre = _sobre(cliente_b, almacen, producto, metodo_efectivo, moneda_usd, client_uuid="venta-cli-ajeno")
    r = client_a.post(URL, sobre, format="json", **_hdr("venta-cli-ajeno"))
    assert r.status_code == 422, r.data
    assert "id_cliente" in r.data["error"]
    assert _count_notas(empresa_a) == 0


def test_caja_virtual_ajena_rechaza(
    client_a, empresa_a, empresa_b, user_a, moneda_usd, metodo_efectivo
):
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
