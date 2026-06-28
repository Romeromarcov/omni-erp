"""Tests de la Fase 5 — sync Odoo → espejo (SOLO LECTURA).

Usa un ``execute`` FALSO que despacha por (modelo, método) y devuelve registros
Odoo canónicos. NO requiere Odoo real ni red. Cubre:
  - sync completo con mapeo correcto (marca fallback, categoría raíz, entrega
    completa, devolución, qty neta, monto_facturado USD, NCs out_refund,
    vendedor por login, es_primera_compra);
  - idempotencia (upsert, sin duplicados);
  - separación de mundos (no toca Vinculacion/Bandeja/Conciliacion);
  - aislamiento multi-tenant;
  - unit tests del reader (cada leer_*);
  - fábrica de producción execute_para_empresa (mock + error claro).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.cxc_lubrikca.models import (
    BandejaFacturacion,
    ConciliacionLubrikca,
    LineaPedidoLubrikca,
    PagoLubrikca,
    PedidoLubrikca,
    PrecioListaLubrikca,
    Vinculacion,
)
from apps.cxc_lubrikca.services.odoo_reader import (
    MARCA_FALLBACK,
    LubrikcaOdooReader,
    _date_str,
    _datetime_str,
    _dec,
    _m2o_id,
    _m2o_name,
    execute_para_empresa,
)
from apps.cxc_lubrikca.services.sync import (
    SyncError,
    sincronizar_desde_odoo,
    sincronizar_empresa,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fake executor — datos Odoo canónicos
# ---------------------------------------------------------------------------
def _odoo_dataset():
    """Registros Odoo de ejemplo (formato XML-RPC: m2o como [id, name])."""
    return {
        ("sale.order", "search_read"): [
            {
                "id": 1,
                "name": "S00553",
                "partner_id": [10, "Cliente Uno"],
                "date_order": "2026-06-01 09:00:00",
                "amount_total": 1650.44,
                "pricelist_id": [5, "Precio USD Pago VES"],
                "user_id": [8, "Rep Ruta 3"],
                "delivery_status": "full",
                "invoice_status": "invoiced",
                "state": "sale",
            },
        ],
        ("sale.order", "search_count"): 1,  # es_primera_compra = True
        ("res.users", "read"): [
            {"id": 8, "login": "rep3@lubrikca.com"},
        ],
        ("sale.order.line", "search_read"): [
            {
                "id": 101,
                "order_id": [1, "S00553"],
                "product_id": [200, "Aceite 20W50"],
                "product_uom_qty": 10.0,
                "price_unit": 5.5,
                "qty_delivered": 8.0,  # neta de devoluciones
            },
            {
                "id": 102,
                "order_id": [1, "S00553"],
                "product_id": [201, "Filtro X"],
                "product_uom_qty": 2.0,
                "price_unit": 3.0,
                "qty_delivered": 2.0,
            },
        ],
        ("product.product", "read"): [
            {"id": 200, "brand_id": [1, "Global Oil"], "categ_id": [4, "Comercial / Lubricantes"]},
            {"id": 201, "brand_id": False, "categ_id": [5, "Industrial"]},  # sin marca → "*"
        ],
        ("stock.picking", "search_read"): [
            {
                "id": 900,
                "sale_id": [1, "S00553"],
                "date_done": "2026-06-05 14:00:00",
                "scheduled_date": "2026-06-04 08:00:00",
                "state": "done",
                "return_id": False,
            },
            {  # picking de devolución
                "id": 901,
                "sale_id": [1, "S00553"],
                "date_done": "2026-06-06 10:00:00",
                "scheduled_date": False,
                "state": "done",
                "return_id": [900, "Devolución de S00553"],
            },
        ],
        ("account.payment", "search_read"): [
            {
                "id": 5001,
                "partner_id": [10, "Cliente Uno"],
                "amount": 94.0,
                "currency_id": [1, "USD"],
                "journal_id": [29, "Efectivo USD"],
                "date": "2026-06-05 10:30:00",
            },
        ],
        ("res.partner", "read"): [
            {"id": 10, "user_id": [8, "Rep Ruta 3"]},
        ],
        ("account.move", "search_read"): [
            {
                "id": 7001,
                "invoice_origin": "S00553",
                "move_type": "out_invoice",
                "amount_total_signed_usd": 1650.44,
            },
            {
                "id": 7002,
                "invoice_origin": "S00553",
                "move_type": "out_refund",
                "amount_total_signed_usd": -50.0,  # NC; se toma abs
            },
        ],
    }


def make_fake_execute(dataset=None):
    """Devuelve un execute(model, method, args, kwargs) que despacha por dataset."""
    data = dataset if dataset is not None else _odoo_dataset()
    calls = []

    def execute(model, method, args, kwargs):
        calls.append((model, method, args, kwargs))
        # write methods nunca deben invocarse (solo lectura).
        assert method in {"search_read", "read", "search_count"}, (
            f"método de escritura prohibido: {model}.{method}"
        )
        return data.get((model, method), [] if method != "search_count" else 0)

    execute.calls = calls  # type: ignore[attr-defined]
    return execute


# ---------------------------------------------------------------------------
# Sync completo
# ---------------------------------------------------------------------------
def test_sync_completo_mapea_todo(empresa_a):
    reader = LubrikcaOdooReader(make_fake_execute())
    sincronizar_desde_odoo(empresa_a, reader)

    ped = PedidoLubrikca.objects.get(empresa=empresa_a, so_id="S00553")
    assert ped.cliente_externo_id == "10"
    assert ped.vendedor_email == "rep3@lubrikca.com"
    assert ped.fecha == date(2026, 6, 1)
    assert ped.lista_precios == "5"
    assert ped.es_primera_compra is True
    assert ped.estado_entrega == "full"
    assert ped.entregada_completa is True
    assert ped.fecha_entrega == date(2026, 6, 6)  # date_done más reciente
    assert ped.tiene_devolucion is True
    assert ped.facturada is True
    assert ped.factura_id == "7001"
    assert ped.monto_facturado == Decimal("1650.44")
    assert ped.ncs_facturadas == Decimal("50.00")

    lineas = {l.linea_id: l for l in ped.lineas.all()}
    assert lineas["101"].marca == "Global Oil"
    assert lineas["101"].categoria == "Comercial"  # raíz del árbol
    assert lineas["101"].cantidad_entregada == Decimal("8")
    assert lineas["102"].marca == MARCA_FALLBACK  # sin brand → "*"
    assert lineas["102"].categoria == "Industrial"

    pago = PagoLubrikca.objects.get(empresa=empresa_a, pago_id="5001")
    assert pago.monto == Decimal("94")
    assert pago.moneda == "USD"
    assert pago.metodo_pago == "29"
    assert pago.vendedor_email == "rep3@lubrikca.com"

    # Precios: 2 productos distintos en la lista 5 → 2 filas.
    assert PrecioListaLubrikca.objects.filter(empresa=empresa_a).count() == 2
    precio = PrecioListaLubrikca.objects.get(
        empresa=empresa_a, producto="Aceite 20W50", lista="5"
    )
    assert precio.precio == Decimal("5.5")


def test_sync_counts_exactos(empresa_a):
    reader = LubrikcaOdooReader(make_fake_execute())
    counts = sincronizar_desde_odoo(empresa_a, reader)
    assert counts["pedidos"] == 1
    assert counts["lineas"] == 2
    assert counts["pagos"] == 1
    assert counts["precios"] == 2
    assert counts["facturas"] == 1


def test_sync_idempotente(empresa_a):
    reader = LubrikcaOdooReader(make_fake_execute())
    sincronizar_desde_odoo(empresa_a, reader)
    sincronizar_desde_odoo(empresa_a, LubrikcaOdooReader(make_fake_execute()))

    assert PedidoLubrikca.objects.filter(empresa=empresa_a).count() == 1
    assert LineaPedidoLubrikca.objects.filter(empresa=empresa_a).count() == 2
    assert PagoLubrikca.objects.filter(empresa=empresa_a).count() == 1
    assert PrecioListaLubrikca.objects.filter(empresa=empresa_a).count() == 2


def test_sync_no_toca_tablas_de_trabajo_humano(empresa_a):
    # Pre-cargar un pedido espejo + Vinculacion/Bandeja/Conciliacion.
    ped = PedidoLubrikca.objects.create(
        empresa=empresa_a,
        so_id="S00553",
        cliente_externo_id="10",
        fecha=date(2026, 6, 1),
        lista_precios="5",
    )
    pago = PagoLubrikca.objects.create(
        empresa=empresa_a,
        pago_id="P-PRE",
        cliente_externo_id="10",
        monto=Decimal("10"),
        moneda="USD",
        metodo_pago="29",
        fecha_pago="2026-06-05T10:00:00Z",
    )
    Vinculacion.objects.create(
        empresa=empresa_a,
        pedido=ped,
        pago=pago,
        monto_aplicado=Decimal("10"),
        hora_pago_confirmada="2026-06-05T10:00:00Z",
        tasa_bcv_aplicada=Decimal("36"),
        tasa_binance_aplicada=Decimal("40"),
        moneda_abono="USD",
    )
    BandejaFacturacion.objects.create(
        empresa=empresa_a,
        pedido=ped,
        lista_aplicada="5",
        precio_base_calculado=Decimal("100"),
        total_motor=Decimal("100"),
    )
    ConciliacionLubrikca.objects.create(
        empresa=empresa_a,
        pedido=ped,
        total_motor=Decimal("100"),
        monto_facturado=Decimal("100"),
        ncs=Decimal("0"),
        diferencia=Decimal("0"),
        resultado="verde",
    )

    v_before = Vinculacion.objects.count()
    b_before = BandejaFacturacion.objects.count()
    c_before = ConciliacionLubrikca.objects.count()

    sincronizar_desde_odoo(empresa_a, LubrikcaOdooReader(make_fake_execute()))

    assert Vinculacion.objects.count() == v_before
    assert BandejaFacturacion.objects.count() == b_before
    assert ConciliacionLubrikca.objects.count() == c_before


def test_sync_multitenant_solo_empresa_dada(empresa_a, empresa_b):
    sincronizar_desde_odoo(empresa_a, LubrikcaOdooReader(make_fake_execute()))

    assert PedidoLubrikca.objects.filter(empresa=empresa_a).count() == 1
    assert PedidoLubrikca.objects.filter(empresa=empresa_b).count() == 0
    assert PagoLubrikca.objects.filter(empresa=empresa_b).count() == 0
    assert PrecioListaLubrikca.objects.filter(empresa=empresa_b).count() == 0


def test_sync_pedido_no_facturado_sin_factura(empresa_a):
    data = _odoo_dataset()
    data[("sale.order", "search_read")][0]["invoice_status"] = "to invoice"
    data[("account.move", "search_read")] = []  # sin facturas
    reader = LubrikcaOdooReader(make_fake_execute(data))
    sincronizar_desde_odoo(empresa_a, reader)

    ped = PedidoLubrikca.objects.get(empresa=empresa_a, so_id="S00553")
    assert ped.facturada is False
    assert ped.monto_facturado is None
    assert ped.ncs_facturadas == Decimal("0")


def test_sync_entrega_parcial_sin_fecha(empresa_a):
    data = _odoo_dataset()
    data[("sale.order", "search_read")][0]["delivery_status"] = "partial"
    reader = LubrikcaOdooReader(make_fake_execute(data))
    sincronizar_desde_odoo(empresa_a, reader)

    ped = PedidoLubrikca.objects.get(empresa=empresa_a, so_id="S00553")
    assert ped.entregada_completa is False
    assert ped.fecha_entrega is None  # solo se ancla con entrega completa


# ---------------------------------------------------------------------------
# Reader — unit tests por método
# ---------------------------------------------------------------------------
def test_reader_leer_pedidos_mapea():
    reader = LubrikcaOdooReader(make_fake_execute())
    pedidos = reader.leer_pedidos()
    assert len(pedidos) == 1
    p = pedidos[0]
    assert p["so_id"] == "S00553"
    assert p["cliente_externo_id"] == "10"
    assert p["vendedor_email"] == "rep3@lubrikca.com"
    assert p["lista_precios"] == "5"
    assert p["es_primera_compra"] is True
    assert p["estado_entrega"] == "full"
    assert p["monto_total"] == Decimal("1650.44")


def test_reader_leer_pedidos_vacio():
    reader = LubrikcaOdooReader(make_fake_execute({}))
    assert reader.leer_pedidos() == []


def test_reader_leer_pedidos_no_primera_compra():
    data = _odoo_dataset()
    data[("sale.order", "search_count")] = 3  # ya tiene varias SO
    reader = LubrikcaOdooReader(make_fake_execute(data))
    p = reader.leer_pedidos()[0]
    assert p["es_primera_compra"] is False


def test_reader_leer_lineas_marca_y_categoria_raiz():
    reader = LubrikcaOdooReader(make_fake_execute())
    lineas = reader.leer_lineas(["S00553"])
    by_id = {l["linea_id"]: l for l in lineas}
    assert by_id["101"]["marca"] == "Global Oil"
    assert by_id["101"]["categoria"] == "Comercial"
    assert by_id["101"]["cantidad_entregada"] == Decimal("8")
    assert by_id["102"]["marca"] == MARCA_FALLBACK
    assert by_id["102"]["categoria"] == "Industrial"


def test_reader_leer_lineas_sin_so_names():
    reader = LubrikcaOdooReader(make_fake_execute())
    assert reader.leer_lineas([]) == []


def test_reader_leer_entregas_full_y_devolucion():
    reader = LubrikcaOdooReader(make_fake_execute())
    entregas = reader.leer_entregas(["S00553"])
    info = entregas["S00553"]
    assert info["entregada_completa"] is True
    assert info["tiene_devolucion"] is True
    assert info["fecha_entrega"] == "2026-06-06"  # más reciente


def test_reader_leer_entregas_vacio():
    reader = LubrikcaOdooReader(make_fake_execute())
    assert reader.leer_entregas([]) == {}


def test_reader_leer_pagos_mapea():
    reader = LubrikcaOdooReader(make_fake_execute())
    pagos = reader.leer_pagos()
    assert len(pagos) == 1
    pg = pagos[0]
    assert pg["pago_id"] == "5001"
    assert pg["moneda"] == "USD"
    assert pg["metodo_pago"] == "29"
    assert pg["vendedor_email"] == "rep3@lubrikca.com"
    assert pg["monto"] == Decimal("94")


def test_reader_leer_pagos_ves():
    data = _odoo_dataset()
    data[("account.payment", "search_read")][0]["currency_id"] = [166, "VES"]
    reader = LubrikcaOdooReader(make_fake_execute(data))
    assert reader.leer_pagos()[0]["moneda"] == "VES"


def test_reader_leer_pagos_vacio():
    reader = LubrikcaOdooReader(make_fake_execute({}))
    assert reader.leer_pagos() == []


def test_reader_leer_facturas_usd_y_ncs():
    reader = LubrikcaOdooReader(make_fake_execute())
    facturas = reader.leer_facturas(["S00553"])
    info = facturas["S00553"]
    assert info["monto_facturado_usd"] == Decimal("1650.44")
    assert info["ncs"] == Decimal("50.0")
    assert info["factura_id"] == "7001"


def test_reader_leer_facturas_vacio():
    reader = LubrikcaOdooReader(make_fake_execute())
    assert reader.leer_facturas([]) == {}


def test_reader_delta_desde_agrega_dominio():
    ex = make_fake_execute()
    reader = LubrikcaOdooReader(ex)
    reader.leer_pedidos(desde="2026-06-01 00:00:00")
    reader.leer_pagos(desde="2026-06-01 00:00:00")
    # el dominio de write_date debe propagarse en la 1ª posición de args
    so_call = next(c for c in ex.calls if c[0] == "sale.order" and c[1] == "search_read")
    assert ["write_date", ">", "2026-06-01 00:00:00"] in so_call[2][0]


# ---------------------------------------------------------------------------
# Fábrica de producción
# ---------------------------------------------------------------------------
def test_execute_para_empresa_sin_conector_levanta_syncerror(empresa_a):
    with pytest.raises(SyncError):
        execute_para_empresa(empresa_a)


def test_sincronizar_empresa_sin_conector_levanta_syncerror(empresa_a):
    with pytest.raises(SyncError):
        sincronizar_empresa(empresa_a)


def test_execute_para_empresa_usa_conector(empresa_a, monkeypatch):
    """Con un conector Odoo activo, devuelve client.call (mockeado, sin red)."""
    import apps.cxc_lubrikca.services.odoo_reader as mod

    class _FakeClient:
        def call(self, *a, **k):
            return "CALLED"

    class _FakeConnector:
        def _get_client(self):
            return _FakeClient()

    class _FakeInstancia:
        pass

    class _FakeQS:
        def select_related(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return _FakeInstancia()

    class _FakeManager:
        objects = _FakeQS()

    class _FakeRegistry:
        def get_connector(self, instancia):
            return _FakeConnector()

    import apps.integration_hub.connectors.registry as reg_mod
    import apps.integration_hub.models as ih_models

    monkeypatch.setattr(ih_models, "ConectorInstancia", _FakeManager, raising=False)
    monkeypatch.setattr(reg_mod, "registry", _FakeRegistry(), raising=False)

    fn = mod.execute_para_empresa(empresa_a)
    assert fn("sale.order", "search_read", [[]], {}) == "CALLED"


# ---------------------------------------------------------------------------
# Helpers puros del reader (cubren ramas de normalización Odoo)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_m2o_helpers():
    assert _m2o_id([7, "X"]) == "7"
    assert _m2o_id(False) == ""
    assert _m2o_id(None) == ""
    assert _m2o_id(42) == "42"  # escalar
    assert _m2o_name([7, "X"]) == "X"
    assert _m2o_name(False) == ""
    assert _m2o_name(None) == ""
    assert _m2o_name("plain") == "plain"


@pytest.mark.django_db
def test_dec_helper():
    assert _dec(False) == Decimal("0")
    assert _dec("") == Decimal("0")
    assert _dec("3.14") == Decimal("3.14")
    assert _dec("no-numero") == Decimal("0")  # InvalidOperation → 0


@pytest.mark.django_db
def test_date_helpers():
    assert _date_str(False) is None
    assert _date_str("2026-06-05 10:00:00") == "2026-06-05"
    assert _datetime_str(None) is None
    assert _datetime_str("2026-06-05 10:00:00") == "2026-06-05 10:00:00"


# ---------------------------------------------------------------------------
# Ramas de borde del reader
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_reader_leer_lineas_recs_vacias():
    """so_names no vacío pero Odoo no devuelve líneas → []."""
    data = _odoo_dataset()
    data[("sale.order.line", "search_read")] = []
    reader = LubrikcaOdooReader(make_fake_execute(data))
    assert reader.leer_lineas(["S00553"]) == []


@pytest.mark.django_db
def test_reader_leer_lineas_sin_product_id():
    """Línea sin product_id → marca/categoría fallback; _read no se llama con ids."""
    data = _odoo_dataset()
    data[("sale.order.line", "search_read")] = [
        {
            "id": 1,
            "order_id": [1, "S00553"],
            "product_id": False,
            "product_uom_qty": 1.0,
            "price_unit": 2.0,
            "qty_delivered": 1.0,
        }
    ]
    reader = LubrikcaOdooReader(make_fake_execute(data))
    ln = reader.leer_lineas(["S00553"])[0]
    assert ln["marca"] == MARCA_FALLBACK
    assert ln["categoria"] == "*"


@pytest.mark.django_db
def test_reader_categoria_fallback_estrella():
    """Producto sin categ_id → categoría '*'."""
    data = _odoo_dataset()
    data[("product.product", "read")] = [
        {"id": 200, "brand_id": False, "categ_id": False},
        {"id": 201, "brand_id": False, "categ_id": False},
    ]
    reader = LubrikcaOdooReader(make_fake_execute(data))
    lineas = reader.leer_lineas(["S00553"])
    assert all(l["categoria"] == "*" for l in lineas)
    assert all(l["marca"] == MARCA_FALLBACK for l in lineas)


@pytest.mark.django_db
def test_reader_categoria_raiz_vacia_cae_a_estrella():
    """categ_id cuyo primer segmento es vacío (' / Sub') → '*'."""
    data = _odoo_dataset()
    data[("product.product", "read")] = [
        {"id": 200, "brand_id": False, "categ_id": [4, " / Subnivel"]},
        {"id": 201, "brand_id": False, "categ_id": [5, "Industrial"]},
    ]
    reader = LubrikcaOdooReader(make_fake_execute(data))
    by_id = {l["linea_id"]: l for l in reader.leer_lineas(["S00553"])}
    assert by_id["101"]["categoria"] == "*"


@pytest.mark.django_db
def test_reader_entregas_picking_sin_sale_id_se_ignora():
    data = _odoo_dataset()
    data[("stock.picking", "search_read")] = [
        {"id": 900, "sale_id": False, "date_done": "2026-06-05", "state": "done", "return_id": False},
    ]
    reader = LubrikcaOdooReader(make_fake_execute(data))
    assert reader.leer_entregas(["S00553"]) == {}


@pytest.mark.django_db
def test_reader_facturas_sin_invoice_origin_se_ignora():
    data = _odoo_dataset()
    data[("account.move", "search_read")] = [
        {"id": 1, "invoice_origin": False, "move_type": "out_invoice", "amount_total_signed_usd": 10.0},
    ]
    reader = LubrikcaOdooReader(make_fake_execute(data))
    assert reader.leer_facturas(["S00553"]) == {}


# ---------------------------------------------------------------------------
# Ramas de borde del sync
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_sync_pedido_fecha_invalida_usa_hoy(empresa_a):
    data = _odoo_dataset()
    data[("sale.order", "search_read")][0]["date_order"] = "fecha-mala"
    reader = LubrikcaOdooReader(make_fake_execute(data))
    sincronizar_desde_odoo(empresa_a, reader)
    ped = PedidoLubrikca.objects.get(empresa=empresa_a, so_id="S00553")
    assert ped.fecha is not None  # cae a hoy


@pytest.mark.django_db
def test_sync_pago_fecha_invalida_usa_ahora(empresa_a):
    data = _odoo_dataset()
    data[("account.payment", "search_read")][0]["date"] = "no-fecha"
    reader = LubrikcaOdooReader(make_fake_execute(data))
    sincronizar_desde_odoo(empresa_a, reader)
    pago = PagoLubrikca.objects.get(empresa=empresa_a, pago_id="5001")
    assert pago.fecha_pago is not None


@pytest.mark.django_db
def test_sync_pago_sin_fecha_usa_ahora(empresa_a):
    data = _odoo_dataset()
    data[("account.payment", "search_read")][0]["date"] = False
    reader = LubrikcaOdooReader(make_fake_execute(data))
    sincronizar_desde_odoo(empresa_a, reader)
    assert PagoLubrikca.objects.filter(empresa=empresa_a, pago_id="5001").exists()


@pytest.mark.django_db
def test_sync_pedido_sin_so_id_se_omite(empresa_a):
    data = _odoo_dataset()
    # Pedido con name vacío → so_id "" → se omite en el upsert.
    data[("sale.order", "search_read")][0]["name"] = ""
    reader = LubrikcaOdooReader(make_fake_execute(data))
    counts = sincronizar_desde_odoo(empresa_a, reader)
    assert counts["pedidos"] == 0
    assert PedidoLubrikca.objects.filter(empresa=empresa_a).count() == 0


@pytest.mark.django_db
def test_sync_linea_de_so_ausente_se_omite(empresa_a):
    """Línea cuyo order_id no está en el espejo de la empresa → se omite."""
    data = _odoo_dataset()
    # No hay pedidos, pero sí líneas apuntando a una SO inexistente.
    data[("sale.order", "search_read")] = []
    data[("sale.order.line", "search_read")] = [
        {
            "id": 999,
            "order_id": [99, "S99999"],
            "product_id": [200, "Aceite"],
            "product_uom_qty": 1.0,
            "price_unit": 1.0,
            "qty_delivered": 0.0,
        }
    ]
    reader = LubrikcaOdooReader(make_fake_execute(data))
    counts = sincronizar_desde_odoo(empresa_a, reader)
    assert counts["lineas"] == 0
    assert LineaPedidoLubrikca.objects.filter(empresa=empresa_a).count() == 0


@pytest.mark.django_db
def test_sync_pago_sin_id_se_omite(empresa_a):
    data = _odoo_dataset()
    data[("account.payment", "search_read")][0]["id"] = ""
    reader = LubrikcaOdooReader(make_fake_execute(data))
    counts = sincronizar_desde_odoo(empresa_a, reader)
    assert counts["pagos"] == 0


@pytest.mark.django_db
def test_sincronizar_empresa_usa_factory(empresa_a, monkeypatch):
    """sincronizar_empresa arma el reader de producción vía execute_para_empresa."""
    import apps.cxc_lubrikca.services.sync as sync_mod

    fake_exec = make_fake_execute()
    monkeypatch.setattr(sync_mod, "execute_para_empresa", lambda emp: fake_exec)
    counts = sincronizar_empresa(empresa_a)
    assert counts["pedidos"] == 1
    assert PedidoLubrikca.objects.filter(empresa=empresa_a, so_id="S00553").exists()
