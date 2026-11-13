# ruff: noqa: F811
"""Capa Omni → Odoo de los bots, con un Odoo simulado (sin red)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.bots_ingest.models import IngestaBot
from apps.bots_ingest.services import odoo_push
from apps.crm.models import Cliente
from apps.integration_hub.connectors.base import ConnectorConnectionError
from apps.ventas.models import Pedido

from .test_ingest import _pedido, api, bot_usuario, catalogo, enviar, servicio  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db]


class FakeCli:
    """Cliente Odoo mínimo: ``respuestas`` mapea (modelo, método) → valor o función(args)."""

    def __init__(self, **respuestas):
        self.r = {
            ("res.partner", "search"): [],
            ("res.users", "search"): [4],
            ("sale.order", "search"): [],
            ("sale.order", "read"): [{"name": "S00700"}],
            ("account.payment", "search"): [],
            ("product.product", "search"): [],
        }
        self.r.update(
            {(tuple(k.split(":")) if ":" in k else k): v for k, v in respuestas.items()}
        )
        self.llamadas = []

    def call(self, model, method, args=None, kwargs=None):
        self.llamadas.append((model, method, args))
        v = self.r[(model, method)]
        return v(args) if callable(v) else v

    def get_variantes_producto(self, tmpl_id):
        return self.r.get("variantes", {}).get(tmpl_id, [])

    def get_monedas(self):
        return [{"id": 1, "name": "USD"}, {"id": 2, "name": "VEF"}]

    def get_diarios(self, tipos=None):
        return self.r.get("diarios", [])


class FakeConn:
    def __init__(self, cli):
        self.cli = cli
        self.contactos, self.pedidos, self.pagos = [], [], []

    def _get_client(self):
        return self.cli

    def push_contacto(self, datos):
        self.contactos.append(datos)
        return "55"

    def push_pedido_venta(self, datos):
        self.pedidos.append(datos)
        return "700"

    def push_pago(self, datos):
        self.pagos.append(datos)
        return "900"


class Inst:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}

    def get_config(self):
        return self.cfg


@pytest.fixture
def odoo(monkeypatch):
    """Instala un Odoo simulado y devuelve (conn, instalar(cli, cfg))."""
    estado = {}

    def instalar(cli, cfg=None):
        conn = FakeConn(cli)
        monkeypatch.setattr(odoo_push, "OdooConnector", lambda inst: conn)
        monkeypatch.setattr(odoo_push, "instancia_odoo", lambda empresa: Inst(cfg))
        monkeypatch.setattr(odoo_push, "EntidadSincronizada", _SinMapa)
        estado["conn"] = conn
        return conn

    return instalar


class _SinMapa:
    class objects:  # noqa: N801 - imita el manager sin tocar la BD de sync
        @staticmethod
        def filter(**kw):
            return type("Q", (), {"first": staticmethod(lambda: None)})()


def _pedido_ingesta(api, catalogo):
    _, prod = catalogo
    prod.referencia_externa = "10"
    prod.save()
    r = enviar(api, "pedido", _pedido(), key="p1")
    assert r.status_code == 201, r.data
    return IngestaBot.objects.get(pk=r.data["id_ingesta"])


def test_pedido_crea_contacto_y_pedido_en_odoo(
    api, bot_usuario, catalogo, odoo, empresa_a
):  # noqa: F811
    conn = odoo(FakeCli(variantes={10: [{"id": 900}]}))
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert (
        ing.estado == "SINCRONIZADO"
        and ing.odoo_ref == "sale.order:700"
        and ing.error == ""
    )
    # El cliente se crea en Odoo con su RIF, marca de cliente y el GPS capturado.
    c = conn.contactos[0]
    assert c["identificador_fiscal"] == "J-123456789" and c["es_cliente"] is True
    assert c["latitud"] == Decimal("10.480600")
    cliente = Cliente.objects.get(id_empresa=empresa_a, rif="J-123456789")
    assert cliente.referencia_externa == "55"
    # El pedido usa ids de Odoo: partner, variante de producto, vendedor.
    p = conn.pedidos[0]
    assert p["partner_id"] == 55 and p["vendedor_id"] == 4
    assert p["lineas"][0]["product_id"] == 900 and p["lineas"][0][
        "cantidad"
    ] == Decimal("2.0000")
    # Con el nombre de Odoo la sync entrante lo reconoce (no duplica); queda el número del bot.
    ped = Pedido.objects.get(id_empresa=empresa_a)
    assert ped.numero_pedido == "S00700" and ped.referencia_externa == "700"
    assert ped.documento_json["numero_bot"]


def test_sincronizar_dos_veces_no_duplica(api, bot_usuario, catalogo, odoo):  # noqa: F811
    conn = odoo(FakeCli(variantes={10: [{"id": 900}]}))
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    odoo_push.sincronizar(ing)
    assert len(conn.pedidos) == 1


def test_reintento_tras_fallo_parcial_reutiliza_el_pedido_de_odoo(
    api, bot_usuario, catalogo, odoo
):  # noqa: F811
    conn = odoo(FakeCli(variantes={10: [{"id": 900}]}, **{"sale.order:search": [321]}))
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert conn.pedidos == [] and ing.odoo_ref == "sale.order:321"


def test_cliente_existente_en_odoo_por_rif_no_se_recrea(
    api, bot_usuario, catalogo, odoo
):  # noqa: F811
    conn = odoo(FakeCli(variantes={10: [{"id": 900}]}, **{"res.partner:search": [77]}))
    odoo_push.sincronizar(_pedido_ingesta(api, catalogo))
    assert conn.contactos == [] and conn.pedidos[0]["partner_id"] == 77


def test_rif_duplicado_en_odoo_no_se_adivina(api, bot_usuario, catalogo, odoo):  # noqa: F811
    conn = odoo(
        FakeCli(variantes={10: [{"id": 900}]}, **{"res.partner:search": [1, 2]})
    )
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert (
        conn.pedidos == [] and "2 contactos" in ing.error and ing.estado == "PROCESADO"
    )


def test_producto_inexistente_en_odoo_deja_motivo_legible(
    api, bot_usuario, catalogo, odoo
):  # noqa: F811
    conn = odoo(FakeCli())  # sin variantes ni coincidencia por SKU
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert (
        conn.pedidos == [] and "Aceite 20W50" in ing.error and ing.estado == "PROCESADO"
    )


def test_producto_se_resuelve_por_sku_si_no_hay_mapa(api, bot_usuario, catalogo, odoo):  # noqa: F811
    conn = odoo(FakeCli(**{"product.product:search": [555]}))
    _, prod = catalogo
    r = enviar(api, "pedido", _pedido(), key="p2")
    odoo_push.sincronizar(IngestaBot.objects.get(pk=r.data["id_ingesta"]))
    assert conn.pedidos[0]["lineas"][0]["product_id"] == 555 and prod.sku


def test_sin_conector_odoo_no_hace_nada(api, bot_usuario, catalogo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(odoo_push, "instancia_odoo", lambda empresa: None)
    ing = _pedido_ingesta(api, catalogo)
    assert odoo_push.sincronizar(ing).estado == "PROCESADO"


def test_empujar_bots_false_lo_desactiva(api, bot_usuario, catalogo, odoo):  # noqa: F811
    conn = odoo(FakeCli(), {"empujar_bots": False})
    odoo_push.sincronizar(_pedido_ingesta(api, catalogo))
    assert conn.pedidos == []


def test_caida_de_odoo_es_transitoria(api, bot_usuario, catalogo, odoo, monkeypatch):  # noqa: F811
    odoo(FakeCli(variantes={10: [{"id": 900}]}))

    class Cae(FakeConn):
        def _get_client(self):
            raise ConnectorConnectionError("sin conexión")

    monkeypatch.setattr(odoo_push, "OdooConnector", lambda inst: Cae(None))
    with pytest.raises(odoo_push.ErrorTransitorio):
        odoo_push.sincronizar(_pedido_ingesta(api, catalogo))


# ── pagos ────────────────────────────────────────────────────────────────────


def _pago(api, **kw):
    key = kw.pop("k", "pg1")
    d = {
        "rif": "J-123456789",
        "monto": "100",
        "moneda": "USD",
        "referencia": "R1",
        "metodo_pago": "Transferencia",
    }
    d.update(kw)
    return IngestaBot.objects.get(pk=enviar(api, "pago", d, key=key).data["id_ingesta"])


@pytest.fixture
def cliente_odoo(empresa_a):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Taller",
        rif="J-123456789",
        referencia_externa="55",
    )


def test_pago_de_cliente_queda_en_borrador_en_odoo(
    api, bot_usuario, cliente_odoo, odoo
):  # noqa: F811
    conn = odoo(FakeCli(), {"diarios_pago": {"default": 12}})
    ing = _pago(api)
    assert ing.estado == "BORRADOR"
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert ing.estado == "SINCRONIZADO" and ing.odoo_ref == "account.payment:900"
    p = conn.pagos[0]
    assert (p["partner_id"], p["journal_id"], p["moneda_id"], p["tipo"]) == (
        55,
        12,
        1,
        "cliente",
    )
    assert (
        p["monto"] == Decimal("100")
        and "BOT-" in p["referencia"]
        and "ref R1" in p["referencia"]
    )


def test_diario_especifico_por_metodo_y_moneda(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    cfg = {"diarios_pago": {"default": 12, "transferencia_usd": 21}}
    conn = odoo(FakeCli(), cfg)
    odoo_push.sincronizar(_pago(api))
    assert conn.pagos[0]["journal_id"] == 21


def test_diario_sin_config_se_autodetecta_si_es_unico(
    api, bot_usuario, cliente_odoo, odoo
):  # noqa: F811
    conn = odoo(
        FakeCli(
            diarios=[
                {"id": 8, "currency_id": [1, "USD"]},
                {"id": 9, "currency_id": [2, "VEF"]},
            ]
        )
    )
    odoo_push.sincronizar(_pago(api))
    assert conn.pagos[0]["journal_id"] == 8


def test_diario_ambiguo_pide_configurar(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    conn = odoo(
        FakeCli(
            diarios=[{"id": 8, "currency_id": False}, {"id": 9, "currency_id": False}]
        )
    )
    ing = _pago(api)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert conn.pagos == [] and "diarios_pago" in ing.error


def test_pago_ve_con_alias_bs_usa_la_moneda_ves(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    conn = odoo(FakeCli(), {"diarios_pago": {"default": 12}})
    odoo_push.sincronizar(_pago(api, moneda="Bs"))
    assert conn.pagos[0]["moneda_id"] == 2


def test_cliente_del_pago_sin_odoo_no_se_crea(api, bot_usuario, empresa_a, odoo):  # noqa: F811
    Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Taller", rif="J-123456789"
    )
    conn = odoo(FakeCli(), {"diarios_pago": {"default": 12}})
    ing = _pago(api)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert (
        conn.contactos == [] and conn.pagos == [] and "no existe en Odoo" in ing.error
    )


def test_pago_incompleto_no_se_empuja(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    conn = odoo(FakeCli())
    ing = _pago(api, referencia=None)
    assert ing.estado == "INCOMPLETO"
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert conn.pagos == [] and "Faltan datos" in ing.error


def test_pago_a_proveedor_es_outbound(api, bot_usuario, odoo):  # noqa: F811
    conn = odoo(
        FakeCli(**{"res.partner:search": [31]}), {"diarios_pago": {"default": 12}}
    )
    r = enviar(
        api,
        "pago_proveedor",
        {"proveedor": "Lubricantes SA", "monto": "900", "moneda": "USD"},
        key="pp",
    )
    ing = IngestaBot.objects.get(pk=r.data["id_ingesta"])
    odoo_push.sincronizar(ing)
    assert conn.pagos[0]["tipo"] == "proveedor" and conn.pagos[0]["partner_id"] == 31


def test_proveedor_ambiguo_no_se_adivina(api, bot_usuario, odoo):  # noqa: F811
    conn = odoo(
        FakeCli(**{"res.partner:search": [31, 32]}),
        {"diarios_pago": {"default": 12}},
    )
    r = enviar(
        api,
        "pago_proveedor",
        {"proveedor": "Lubricantes SA", "monto": "900", "moneda": "USD"},
        key="pp",
    )
    ing = IngestaBot.objects.get(pk=r.data["id_ingesta"])
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert conn.pagos == [] and "ambiguo" in ing.error


def test_reintento_de_pago_reutiliza_el_existente_en_odoo(
    api, bot_usuario, cliente_odoo, odoo
):  # noqa: F811
    conn = odoo(
        FakeCli(**{"account.payment:search": [444]}),
        {"diarios_pago": {"default": 12}},
    )
    ing = _pago(api)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert conn.pagos == [] and ing.odoo_ref == "account.payment:444"


# ── disparo automático y endpoint ────────────────────────────────────────────


def test_pedido_y_pago_completo_se_encolan_al_confirmar(
    api, bot_usuario, catalogo, cliente_odoo, django_capture_on_commit_callbacks
):  # noqa: F811
    with patch("apps.bots_ingest.tasks.encolar_sync") as enc:
        with django_capture_on_commit_callbacks(execute=True):
            enviar(api, "pedido", _pedido(), key="a")
            enviar(
                api,
                "pago",
                {
                    "rif": "J-123456789",
                    "monto": "1",
                    "moneda": "USD",
                    "referencia": "R",
                },
                key="b",
            )
            enviar(
                api,
                "pago",
                {"rif": "J-123456789", "monto": "1", "moneda": "USD"},
                key="c",
            )  # incompleto
            enviar(
                api,
                "contacto",
                {
                    "nombre": "P",
                    "telefono": "04141234567",
                    "ubicacion": {"latitud": 1, "longitud": 1},
                },
                key="d",
            )
    assert enc.call_count == 2  # solo el pedido y el pago completo


def test_completar_un_pago_lo_encola(
    api, bot_usuario, cliente_odoo, django_capture_on_commit_callbacks
):  # noqa: F811
    ing = _pago(api, referencia=None)
    with patch("apps.bots_ingest.tasks.encolar_sync") as enc:
        with django_capture_on_commit_callbacks(execute=True):
            r = api.post(
                f"/api/bots/ingest/{ing.pk}/completar/",
                {"cambios": {"referencia": "R9"}},
                format="json",
            )
    assert r.status_code == 200 and enc.call_count == 1


def test_endpoint_sincronizar(api, bot_usuario, catalogo, cliente_odoo):  # noqa: F811
    ing = _pedido_ingesta(api, catalogo)
    with patch("apps.bots_ingest.tasks.encolar_sync") as enc:
        r = api.post(f"/api/bots/ingest/{ing.pk}/sincronizar/")
        assert r.status_code == 202 and enc.call_count == 1
    contacto = IngestaBot.objects.get(
        pk=enviar(
            api,
            "contacto",
            {
                "nombre": "P",
                "telefono": "04141234567",
                "ubicacion": {"latitud": 1, "longitud": 1},
            },
            key="z",
        ).data["id_ingesta"]
    )
    assert api.post(f"/api/bots/ingest/{contacto.pk}/sincronizar/").status_code == 422
    IngestaBot.objects.filter(pk=ing.pk).update(estado="SINCRONIZADO")
    assert api.post(f"/api/bots/ingest/{ing.pk}/sincronizar/").status_code == 409
    inc = _pago(api, referencia=None, k="pg9")
    assert api.post(f"/api/bots/ingest/{inc.pk}/sincronizar/").status_code == 422
