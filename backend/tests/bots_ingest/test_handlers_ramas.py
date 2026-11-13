"""Handlers de ingesta: validaciones y ramas de error de contacto, pedido, pago a proveedor y evento.

Usa los fixtures de ``conftest.py`` y los borradores de ``helpers.py`` para ejercitar lo que ``test_ingest.py``
archivo no cubre: datos mal formados, precios ausentes, listas de precio del cliente y errores de
calendario.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.bots_ingest.helpers import UBIC, enviar, pedido_draft
from tests.factories.comercial import ProductoFactory

from apps.bots_ingest.services import handlers
from apps.core.models import Contacto
from apps.crm.models import Cliente
from apps.proveedores.models import Proveedor
from apps.ventas.models import DetallePrecio, ListaPrecio, Pedido

pytestmark = [pytest.mark.django_db]


# ── Utilidades internas ──────────────────────────────────────────────────────


def test_un_decimal_invalido_se_reporta_con_su_nombre():
    with pytest.raises(handlers.HandlerError) as exc:
        handlers._dec("abc", "Cantidad de aceite")
    assert "Cantidad de aceite" in str(exc.value)


def test_sin_ubicacion_no_hay_gps():
    assert handlers._gps(None) == {}
    assert handlers._gps({}) == {}


@pytest.mark.parametrize(
    "ubicacion",
    [{"latitud": "10.4"}, {"longitud": "-66.9"}, {"latitud": "abc", "longitud": "-66.9"}],
)
def test_una_ubicacion_incompleta_o_no_numerica_se_rechaza(ubicacion):
    with pytest.raises(handlers.HandlerError, match="Ubicación GPS inválida"):
        handlers._gps(ubicacion)


def test_buscar_cliente_por_rif_tolera_un_rif_que_no_se_puede_normalizar(empresa_a):
    cli = Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Taller Uno", rif="J-123456789"
    )
    assert handlers._buscar_cliente(empresa_a, rif="j-123456789").pk == cli.pk
    # Un RIF basura no debe lanzar: simplemente no encuentra a nadie.
    assert handlers._buscar_cliente(empresa_a, rif="???") is None


# ── Contacto ─────────────────────────────────────────────────────────────────


def test_contacto_con_telefono_invalido_pide_el_telefono(api, bot_usuario):
    r = enviar(api, "contacto", {"nombre": "Pedro", "telefono": "123", "ubicacion": UBIC})
    assert r.status_code == 422
    assert "telefono" in r.data["faltan"]


def test_contacto_con_ubicacion_invalida_se_rechaza(api, bot_usuario):
    r = enviar(
        api,
        "contacto",
        {"nombre": "Pedro", "telefono": "0414-1234567", "ubicacion": {"latitud": "x", "longitud": "y"}},
    )
    assert r.status_code == 422
    assert "Ubicación GPS inválida" in r.data["error"]


# ── Pedido ───────────────────────────────────────────────────────────────────


def test_pedido_con_fecha_de_entrega_invalida_pide_la_fecha(api, bot_usuario, catalogo):
    r = enviar(api, "pedido", pedido_draft(fecha_entrega="31/12/2026"))
    assert r.status_code == 422
    assert "fecha_entrega" in r.data["faltan"]
    assert Pedido.objects.count() == 0


def test_pedido_con_fecha_de_entrega_valida_la_guarda(api, bot_usuario, catalogo, empresa_a):
    r = enviar(api, "pedido", pedido_draft(fecha_entrega="2026-12-31"))
    assert r.status_code == 201, r.data
    assert Pedido.objects.get(id_empresa=empresa_a).fecha_cierre_estimada.isoformat() == "2026-12-31"


def test_pedido_con_cantidad_cero_se_rechaza(api, bot_usuario, catalogo):
    r = enviar(api, "pedido", pedido_draft(lineas=[{"producto": "AC-20W50", "cantidad": "0"}]))
    assert r.status_code == 422
    assert "cantidad" in r.data["error"].lower()
    assert Pedido.objects.count() == 0


def test_pedido_con_cantidad_no_numerica_se_rechaza(api, bot_usuario, catalogo):
    r = enviar(api, "pedido", pedido_draft(lineas=[{"producto": "AC-20W50", "cantidad": "abc"}]))
    assert r.status_code == 422
    assert "inválid" in r.data["error"].lower()


def test_pedido_de_un_producto_sin_precio_en_la_lista_se_rechaza(
    api, bot_usuario, catalogo, empresa_a
):
    ProductoFactory(id_empresa=empresa_a, nombre_producto="Sin precio", sku="SP-1")
    r = enviar(api, "pedido", pedido_draft(lineas=[{"producto": "SP-1", "cantidad": "1"}]))
    assert r.status_code == 422
    assert "no está en la lista del cliente" in r.data["error"]
    assert Pedido.objects.count() == 0


def test_el_pedido_usa_la_lista_de_precios_del_contacto_del_cliente(
    api, bot_usuario, catalogo, empresa_a, moneda_usd
):
    """Si el cliente tiene una lista propia, manda sobre la lista de referencia."""
    _, producto = catalogo
    lista_vip = ListaPrecio.objects.create(
        id_empresa=empresa_a, nombre="VIP", codigo="VIP", id_moneda=moneda_usd
    )
    DetallePrecio.objects.create(id_lista=lista_vip, id_producto=producto, precio=Decimal("20.00"))
    contacto = Contacto.objects.create(
        id_empresa=empresa_a,
        nombre="Taller VIP",
        rif="J-111111111",
        es_cliente=True,
        lista_precio=lista_vip,
    )
    Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Taller VIP", rif="J-111111111", contacto=contacto
    )
    r = enviar(api, "pedido", pedido_draft(cliente="Taller VIP", rif="J-111111111"))
    assert r.status_code == 201, r.data
    # 2 unidades a 20.00 (lista VIP), no a 12.50 (lista de referencia).
    assert Pedido.objects.get(id_empresa=empresa_a).detalles.get().subtotal == Decimal("40.0000")


# ── Pago a proveedor ─────────────────────────────────────────────────────────


def test_pago_a_un_proveedor_conocido_guarda_su_referencia(api, bot_usuario, empresa_a):
    prov = Proveedor.objects.create(
        id_empresa=empresa_a, razon_social="Lubricantes SA", rif="J-404040401"
    )
    r = enviar(
        api,
        "pago_proveedor",
        {"proveedor": "lubricantes sa", "monto": "100", "moneda": "USD"},
    )
    assert r.status_code == 201, r.data
    assert r.data["resultado"]["proveedor_id"] == str(prov.pk)


def test_pago_a_un_proveedor_desconocido_avisa_pero_no_falla(api, bot_usuario):
    r = enviar(
        api,
        "pago_proveedor",
        {"proveedor": "Proveedor Fantasma", "monto": "100", "moneda": "USD"},
    )
    assert r.status_code == 201, r.data
    assert "proveedor_id" not in r.data["resultado"]
    assert "no encontrado" in r.data["resultado"]["aviso"].lower()


# ── Evento ───────────────────────────────────────────────────────────────────


def _evento(**kw):
    base = {
        "cliente": "Bodega X",
        "ubicacion": "Av. 1",
        "fecha": "2026-12-01",
        "hora_inicio": "09:00",
        "hora_fin": "12:00",
        "promotoras": 1,
        "igloos": 0,
    }
    base.update(kw)
    return base


def test_evento_con_hora_invalida_se_rechaza(api, bot_usuario, calendario):
    r = enviar(api, "evento", _evento(hora_inicio="25:99"))
    assert r.status_code == 422
    assert "fecha" in r.data["faltan"]


def test_evento_que_termina_antes_de_empezar_se_rechaza(api, bot_usuario, calendario):
    r = enviar(api, "evento", _evento(hora_inicio="12:00", hora_fin="09:00"))
    assert r.status_code == 422
    assert "posterior" in r.data["error"].lower()
