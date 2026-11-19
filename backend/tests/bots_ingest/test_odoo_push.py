# ruff: noqa: F811
"""Capa Omni → Odoo de los bots (7 tipos sincronizables), con un Odoo simulado (sin red)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.bots_ingest.models import BotUsuario, IngestaBot
from apps.bots_ingest.services import odoo_push
from apps.crm.models import Cliente
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.finanzas.models import Moneda
from apps.integration_hub.connectors.base import ConnectorConnectionError, ConnectorError
from apps.integration_hub.connectors.odoo.client import OdooCallError
from apps.proveedores.models import Proveedor
from apps.ventas.models import Pedido

from .test_ingest import _pedido, api, bot_usuario, catalogo, enviar, servicio  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db]


class FakeCli:
    """Cliente Odoo mínimo: ``respuestas`` mapea (modelo, método) → valor o función(args)."""

    def __init__(self, **respuestas):
        self.r = {
            ("res.partner", "search"): [],
            ("res.partner", "create"): 61,
            ("res.users", "search"): [4],
            ("sale.order", "search"): [],
            ("sale.order", "search_read"): [],
            ("sale.order", "read"): [{"name": "S00700"}],
            ("account.payment", "search"): [],
            ("account.payment", "create"): 905,
            ("account.move", "search"): [],
            ("account.move", "create"): 801,
            ("product.product", "search"): [],
        }
        self.r.update({(tuple(k.split(":")) if ":" in k else k): v for k, v in respuestas.items()})
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
    def __init__(self, cli, inst=None):
        self.cli = cli
        self.inst = inst
        self.cfg_efectiva = inst.get_config() if inst is not None else {}
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
        self.cfg = {"empujar_bots": True, **(cfg or {})}

    def get_config(self):
        return self.cfg


@pytest.fixture
def odoo(monkeypatch):
    """Instala un Odoo simulado y devuelve instalar(cli, cfg)."""
    estado = {}

    def instalar(cli, cfg=None):
        holder = {}

        def _fabricar(inst):
            conn = FakeConn(cli, inst=inst)
            holder["conn"] = conn
            return conn

        conn_inicial = FakeConn(cli, inst=Inst(cfg))
        holder["conn"] = conn_inicial
        monkeypatch.setattr(odoo_push, "OdooConnector", _fabricar)
        monkeypatch.setattr(odoo_push, "instancia_odoo", lambda empresa: Inst(cfg))
        monkeypatch.setattr(odoo_push, "EntidadSincronizada", _SinMapa)
        estado["holder"] = holder
        return holder

    return instalar


class _SinMapa:
    class objects:  # noqa: N801 - imita el manager sin tocar la BD de sync
        @staticmethod
        def filter(**kw):
            return type("Q", (), {"first": staticmethod(lambda: None)})()


@pytest.fixture
def monedas_omni():
    usd, _ = Moneda.objects.get_or_create(
        codigo_iso="USD",
        defaults={"nombre": "Dólar", "simbolo": "$", "es_generica": True},
    )
    ves, _ = Moneda.objects.get_or_create(
        codigo_iso="VES",
        defaults={"nombre": "Bolívar", "simbolo": "Bs.", "es_generica": True},
    )
    return usd, ves


def _pedido_ingesta(api, catalogo):
    _, prod = catalogo
    prod.referencia_externa = "10"
    prod.save()
    r = enviar(api, "pedido", _pedido(), key="p1")
    assert r.status_code == 201, r.data
    return IngestaBot.objects.get(pk=r.data["id_ingesta"])


def test_pedido_crea_contacto_y_pedido_en_odoo(api, bot_usuario, catalogo, odoo, empresa_a):  # noqa: F811
    h = odoo(FakeCli(variantes={10: [{"id": 900}]}))
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    conn = h["conn"]
    ing.refresh_from_db()
    assert ing.estado == "SINCRONIZADO" and ing.odoo_ref == "sale.order:700" and ing.error == ""
    c = conn.contactos[0]
    assert c["identificador_fiscal"] == "J-123456789" and c["es_cliente"] is True
    assert c["latitud"] == Decimal("10.480600")
    cliente = Cliente.objects.get(id_empresa=empresa_a, rif="J-123456789")
    assert cliente.referencia_externa == "55"
    p = conn.pedidos[0]
    assert p["partner_id"] == 55 and p["vendedor_id"] == 4
    assert p["lineas"][0]["product_id"] == 900 and p["lineas"][0]["cantidad"] == Decimal("2.0000")
    ped = Pedido.objects.get(id_empresa=empresa_a)
    assert ped.numero_pedido == "S00700" and ped.referencia_externa == "700"
    assert ped.documento_json["numero_bot"]


def test_sincronizar_dos_veces_no_duplica(api, bot_usuario, catalogo, odoo):  # noqa: F811
    h = odoo(FakeCli(variantes={10: [{"id": 900}]}))
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    odoo_push.sincronizar(ing)
    assert len(h["conn"].pedidos) == 1


def test_reintento_tras_fallo_parcial_reutiliza_el_pedido_de_odoo(api, bot_usuario, catalogo, odoo):  # noqa: F811
    h = odoo(FakeCli(variantes={10: [{"id": 900}]}, **{"sale.order:search": [321]}))
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert h["conn"].pedidos == [] and ing.odoo_ref == "sale.order:321"


def test_cliente_existente_en_odoo_por_rif_no_se_recrea(api, bot_usuario, catalogo, odoo):  # noqa: F811
    h = odoo(FakeCli(variantes={10: [{"id": 900}]}, **{"res.partner:search": [77]}))
    odoo_push.sincronizar(_pedido_ingesta(api, catalogo))
    assert h["conn"].contactos == [] and h["conn"].pedidos[0]["partner_id"] == 77


def test_rif_duplicado_en_odoo_no_se_adivina(api, bot_usuario, catalogo, odoo):  # noqa: F811
    h = odoo(FakeCli(variantes={10: [{"id": 900}]}, **{"res.partner:search": [1, 2]}))
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert h["conn"].pedidos == [] and "2 contactos" in ing.error and ing.estado == "PROCESADO"


def test_producto_inexistente_en_odoo_deja_motivo_legible(api, bot_usuario, catalogo, odoo):  # noqa: F811
    h = odoo(FakeCli())
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert h["conn"].pedidos == [] and "Aceite 20W50" in ing.error and ing.estado == "PROCESADO"


def test_producto_se_resuelve_por_sku_si_no_hay_mapa(api, bot_usuario, catalogo, odoo):  # noqa: F811
    h = odoo(FakeCli(**{"product.product:search": [555]}))
    _, prod = catalogo
    r = enviar(api, "pedido", _pedido(), key="p2")
    odoo_push.sincronizar(IngestaBot.objects.get(pk=r.data["id_ingesta"]))
    assert h["conn"].pedidos[0]["lineas"][0]["product_id"] == 555 and prod.sku


def test_sin_conector_odoo_no_hace_nada(api, bot_usuario, catalogo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(odoo_push, "instancia_odoo", lambda empresa: None)
    ing = _pedido_ingesta(api, catalogo)
    assert odoo_push.sincronizar(ing).estado == "PROCESADO"


def test_empujar_bots_false_lo_desactiva(api, bot_usuario, catalogo, odoo):  # noqa: F811
    h = odoo(FakeCli(), {"empujar_bots": False})
    odoo_push.sincronizar(_pedido_ingesta(api, catalogo))
    assert h["conn"].pedidos == []


def test_por_defecto_omni_no_empuja_a_odoo(api, bot_usuario, catalogo, odoo, monkeypatch):  # noqa: F811
    """Mientras CxC sea quien escribe en Odoo, sin ``empujar_bots: true`` explícito Omni no envía nada."""
    h = odoo(FakeCli())
    monkeypatch.setattr(
        odoo_push,
        "instancia_odoo",
        lambda empresa: type("I", (), {"get_config": lambda self: {}})(),
    )
    ing = odoo_push.sincronizar(_pedido_ingesta(api, catalogo))
    assert h["conn"].pedidos == [] and h["conn"].contactos == [] and ing.estado == "PROCESADO"


def test_caida_de_odoo_es_transitoria(api, bot_usuario, catalogo, odoo, monkeypatch):  # noqa: F811
    odoo(FakeCli(variantes={10: [{"id": 900}]}))

    class Cae(FakeConn):
        def _get_client(self):
            raise ConnectorConnectionError("sin conexión")

    monkeypatch.setattr(odoo_push, "OdooConnector", lambda inst: Cae(None))
    with pytest.raises(odoo_push.ErrorTransitorio):
        odoo_push.sincronizar(_pedido_ingesta(api, catalogo))


def test_credenciales_dedicadas_write_user_y_fallo_parcial(api, bot_usuario, catalogo, odoo):  # noqa: F811
    clave_escritura = "wk-" + ("9" * 16)
    h = odoo(
        FakeCli(variantes={10: [{"id": 900}]}),
        {
            "user": "lectura@empresa.com",
            "api_key": "rk",
            "write_user": "bots_borrador@empresa.com",
            "write_api_key": clave_escritura,
        },
    )
    ing = _pedido_ingesta(api, catalogo)
    odoo_push.sincronizar(ing)
    assert h["conn"].cfg_efectiva["user"] == "bots_borrador@empresa.com"
    assert h["conn"].cfg_efectiva["api_key"] == clave_escritura

    # Si solo se define write_user sin write_api_key falla cerrado sin usar la credencial de lectura
    odoo(
        FakeCli(variantes={10: [{"id": 900}]}),
        {"user": "lectura@empresa.com", "api_key": "rk", "write_user": "incompleto"},
    )
    r2 = enviar(api, "pedido", _pedido(), key="p-half-cred")
    ing2 = odoo_push.sincronizar(IngestaBot.objects.get(pk=r2.data["id_ingesta"]))
    assert ing2.estado == "PROCESADO" and "write_api_key" in ing2.error


# ── contacto (borrador en res.partner) ───────────────────────────────────────


def test_contacto_crea_borrador_en_odoo_con_fallback_gps_e_idempotencia(api, bot_usuario, odoo):  # noqa: F811
    creados = []

    def crear_partner(args):
        vals = args[0]
        if "partner_latitude" in vals and len(creados) == 0:
            creados.append("fallo_gps")
            raise OdooCallError("Invalid field 'partner_latitude' on model 'res.partner'")
        creados.append(vals)
        return [601]

    cli = FakeCli(**{"res.partner:create": crear_partner})
    odoo(cli)
    r = enviar(
        api,
        "contacto",
        {
            "nombre": "Ferretería El Clavo",
            "telefono": "0414-5551234",
            "email": "ventas@clavo.com",
            "notas": "Visitar los martes",
            "ubicacion": {"latitud": "10.491000", "longitud": "-66.879000"},
        },
        key="ct-1",
    )
    ing = IngestaBot.objects.get(pk=r.data["id_ingesta"])
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert ing.estado == "SINCRONIZADO" and ing.odoo_ref == "res.partner:601"
    vals = creados[-1]
    assert vals["name"] == "Ferretería El Clavo"
    assert vals["customer_rank"] == 0
    assert "[Borrador Telegram]" in vals["comment"]
    assert "Visitar los martes" in vals["comment"]
    assert vals["ref"] == f"BOT-{ing.pk}"

    # Reintento cuando ya existe en Odoo por marca (ref = BOT-<id>) no vuelve a crear
    cli2 = FakeCli(**{"res.partner:search": [601]})
    odoo(cli2)
    r2 = enviar(
        api,
        "contacto",
        {
            "nombre": "Otro",
            "telefono": "0412-9998877",
            "ubicacion": {"latitud": 10.1, "longitud": -66.1},
        },
        key="ct-2",
    )
    ing2 = odoo_push.sincronizar(IngestaBot.objects.get(pk=r2.data["id_ingesta"]))
    assert ing2.odoo_ref == "res.partner:601"
    assert ("res.partner", "create") not in [(m, fn) for m, fn, _ in cli2.llamadas]


# ── proveedor, factura_proveedor y gasto ─────────────────────────────────────


def test_proveedor_crea_borrador_reutiliza_existente_y_serializa_bloqueo(
    api, bot_usuario, odoo, empresa_a, monkeypatch
):  # noqa: F811
    creados = []
    cli = FakeCli(**{"res.partner:create": lambda args: creados.append(args[0]) or 710})
    odoo(cli)
    r = enviar(
        api,
        "proveedor",
        {
            "nombre": "Distribuidora Oriente C.A.",
            "rif": "J-29888777-1",
            "telefono": "0281-2651122",
            "email": "admin@oriente.ve",
            "direccion": "Av. Intercomunal",
            "dias_credito": 15,
            "notas": "Entrega en planta",
            "ubicacion": {"latitud": "10.180000", "longitud": "-64.680000"},
        },
        key="prov-1",
    )
    ing = IngestaBot.objects.get(pk=r.data["id_ingesta"])
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert ing.estado == "SINCRONIZADO" and ing.odoo_ref == "res.partner:710"
    vals = creados[0]
    assert vals["supplier_rank"] == 1 and vals["customer_rank"] == 0
    assert vals["company_type"] == "company"
    assert vals["vat"] == "J-298887771"
    assert "Días de crédito: 15" in vals["comment"]
    assert vals["partner_latitude"] == pytest.approx(10.18)
    prov = Proveedor.objects.get(id_empresa=empresa_a, rif="J-298887771")
    assert prov.referencia_externa == "710"

    # Proveedor nuevo que ya existe por nombre exacto en Odoo -> vincula sin crear otro partner
    def buscar_por_nombre(args):
        dom = args[0]
        if dom and dom[0][0] == "name":
            return [725]
        return []

    cli_nom = FakeCli(**{"res.partner:search": buscar_por_nombre})
    odoo(cli_nom)
    r_nom = enviar(
        api,
        "proveedor",
        {
            "nombre": "Suministros Del Sur",
            "rif": "V-15222333-4",
            "telefono": "0414-3334455",
        },
        key="prov-2",
    )
    ing_nom = odoo_push.sincronizar(IngestaBot.objects.get(pk=r_nom.data["id_ingesta"]))
    assert ing_nom.odoo_ref == "res.partner:725"

    # Nombre ambiguo en Odoo -> deja motivo legible sin adivinar
    cli_amb = FakeCli(**{"res.partner:search": lambda args: [1, 2] if args[0] and args[0][0][0] == "name" else []})
    odoo(cli_amb)
    r_amb = enviar(
        api,
        "proveedor",
        {
            "nombre": "Duplicado C.A.",
            "rif": "J-40111222-3",
            "telefono": "0414-0001122",
        },
        key="prov-3",
    )
    ing_amb = odoo_push.sincronizar(IngestaBot.objects.get(pk=r_amb.data["id_ingesta"]))
    assert ing_amb.estado == "PROCESADO" and "2 contactos" in ing_amb.error

    # Si otro worker sostiene el advisory lock PostgreSQL -> pg_try_advisory_xact_lock devuelve False -> ErrorTransitorio
    r_lock = enviar(
        api,
        "proveedor",
        {
            "nombre": "Bloqueado C.A.",
            "rif": "J-50111222-3",
            "telefono": "0414-7778899",
        },
        key="prov-lock",
    )
    ing_lock = IngestaBot.objects.get(pk=r_lock.data["id_ingesta"])
    orig_cursor = odoo_push.connection.cursor

    class _ProxyCursor:
        def __init__(self, real):
            self._real = real
            self._es_lock = False

        def __enter__(self):
            self._real.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._real.__exit__(exc_type, exc_val, exc_tb)

        def execute(self, sql, params=None):
            if "pg_try_advisory_xact_lock" in str(sql):
                self._es_lock = True
                return None
            self._es_lock = False
            return self._real.execute(sql, params)

        def fetchone(self):
            if self._es_lock:
                return (False,)
            return self._real.fetchone()

        def __getattr__(self, name):
            return getattr(self._real, name)

    monkeypatch.setattr(odoo_push.connection, "cursor", lambda: _ProxyCursor(orig_cursor()))
    with pytest.raises(odoo_push.ErrorTransitorio):
        odoo_push.sincronizar(ing_lock)


def test_factura_proveedor_y_gasto_crean_account_move_borrador_con_auto_proveedor(
    api, bot_usuario, monedas_omni, odoo, empresa_a
):  # noqa: F811
    partners_creados, moves_creados = [], []
    cli = FakeCli(
        **{
            "res.partner:create": lambda args: partners_creados.append(args[0]) or 810,
            "account.move:create": lambda args: moves_creados.append(args[0]) or 910,
            "account.move:fields_get": {
                "move_type": {},
                "partner_id": {},
                "ref": {},
                "invoice_date": {},
                "invoice_date_due": {},
                "currency_id": {},
                "invoice_line_ids": {},
                "narration": {},
            },
            "account.move.line:fields_get": {"tax_ids": {}},
        }
    )
    odoo(cli)

    # 1. Factura de proveedor completa: auto-crea proveedor en Odoo, usa base_imponible y enlaza CxP
    r_fac = enviar(
        api,
        "factura_proveedor",
        {
            "proveedor": "Envases Carabobo C.A.",
            "rif": "J-30999888-7",
            "numero_factura": "FAC-0091",
            "numero_control": "00-778899",
            "fecha_emision": "2026-11-10",
            "fecha_vencimiento": "2026-12-10",
            "base_imponible": "100.00",
            "iva": "16.00",
            "monto_total": "116.00",
            "moneda": "USD",
            "concepto": "Envases plásticos 1L",
            "orden_ref": "OC-45",
        },
        key="fp-1",
    )
    assert r_fac.status_code == 201, r_fac.data
    ing_fac = odoo_push.sincronizar(IngestaBot.objects.get(pk=r_fac.data["id_ingesta"]))
    assert ing_fac.estado == "SINCRONIZADO" and ing_fac.odoo_ref == "account.move:910"
    assert len(partners_creados) == 1
    assert "creado desde un documento" in partners_creados[0]["comment"]
    mv = moves_creados[0]
    assert mv["move_type"] == "in_invoice"
    assert mv["partner_id"] == 810
    assert mv["ref"] == "FAC-0091"
    assert mv["invoice_date_due"] == "2026-12-10"
    assert mv["invoice_line_ids"][0][2]["price_unit"] == 100.0
    assert mv["invoice_line_ids"][0][2]["tax_ids"] == [(6, 0, [])]
    assert "Control 00-778899" in mv["narration"]
    assert "IVA 16.00" in mv["narration"]
    assert "Orden OC-45" in mv["narration"]
    cxp = CuentaPorPagar.objects.get(pk=ing_fac.resultado["cxp_id"])
    assert cxp.referencia_externa == "910"

    # 2. Gasto al contado sin RIF y sin número de factura: sin vencimiento, nota de contado y categoría
    moves_creados.clear()
    r_gas = enviar(
        api,
        "gasto",
        {
            "proveedor": "Autolavado Rápido",
            "fecha_emision": "2026-11-15",
            "monto_total": "25.50",
            "moneda": "Bs",
            "categoria": "Mantenimiento flota",
        },
        key="ga-1",
    )
    assert r_gas.status_code == 201, r_gas.data
    ing_gas = odoo_push.sincronizar(IngestaBot.objects.get(pk=r_gas.data["id_ingesta"]))
    assert ing_gas.estado == "SINCRONIZADO" and ing_gas.odoo_ref == "account.move:910"
    mv_g = moves_creados[0]
    assert "invoice_date_due" not in mv_g
    assert mv_g["currency_id"] == 2
    assert mv_g["ref"].startswith("S/N-")
    assert "pagado al contado" in mv_g["narration"]
    assert "Categoría Mantenimiento flota" in mv_g["narration"]

    # 3. Factura duplicada ya existente en Odoo para un proveedor ya conocido -> NoSincronizable
    cli_dup = FakeCli(**{"account.move:search": lambda args: [555] if any(c[0] == "ref" for c in args[0]) else []})
    odoo(cli_dup)
    r_dup = enviar(
        api,
        "factura_proveedor",
        {
            "proveedor": "Envases Carabobo C.A.",
            "rif": "J-30999888-7",
            "numero_factura": "FAC-0092",
            "fecha_emision": "2026-11-11",
            "monto_total": "50.00",
            "moneda": "USD",
        },
        key="fp-dup",
    )
    ing_dup = odoo_push.sincronizar(IngestaBot.objects.get(pk=r_dup.data["id_ingesta"]))
    assert ing_dup.estado == "PROCESADO" and "account.move 555" in ing_dup.error


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


def test_pago_de_cliente_queda_en_borrador_en_odoo(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    h = odoo(FakeCli(), {"diarios_pago": {"default": 12}})
    ing = _pago(api)
    assert ing.estado == "BORRADOR"
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert ing.estado == "SINCRONIZADO" and ing.odoo_ref == "account.payment:900"
    p = h["conn"].pagos[0]
    assert (p["partner_id"], p["journal_id"], p["moneda_id"], p["tipo"]) == (
        55,
        12,
        1,
        "cliente",
    )
    assert p["monto"] == Decimal("100") and "BOT-" in p["referencia"] and "ref R1" in p["referencia"]


def test_diario_especifico_por_banco_o_metodo_y_moneda(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    cfg = {
        "diarios_pago": {
            "default": 12,
            "transferencia_usd": 21,
            "bancamiga_ves": 34,
        }
    }
    h = odoo(FakeCli(), cfg)
    odoo_push.sincronizar(_pago(api))
    assert h["conn"].pagos[0]["journal_id"] == 21

    odoo_push.sincronizar(_pago(api, k="pg-banco", moneda="Bs", banco="Bancamiga"))
    assert h["conn"].pagos[0]["journal_id"] == 34


def test_bordes_documentos_compra_idempotencia_y_campos_odoo(api, bot_usuario, monedas_omni, odoo, empresa_a):  # noqa: F811
    # 1. Reintento cuando account.move ya existe en Odoo por marca -> enlaza CxP y no recrea
    cli_prev = FakeCli(
        **{
            "res.partner:search": [810],
            "account.move:search": [950],
        }
    )
    odoo(cli_prev)
    r1 = enviar(
        api,
        "factura_proveedor",
        {
            "proveedor": "Taller Oriente",
            "rif": "J-30111222-3",
            "numero_factura": "F-77",
            "fecha_emision": "2026-11-14",
            "monto_total": "80.00",
            "moneda": "USD",
        },
        key="fp-prev",
    )
    ing1 = odoo_push.sincronizar(IngestaBot.objects.get(pk=r1.data["id_ingesta"]))
    assert ing1.odoo_ref == "account.move:950"
    cxp1 = CuentaPorPagar.objects.get(pk=ing1.resultado["cxp_id"])
    assert cxp1.referencia_externa == "950"

    # Si se invoca _push_documento_compra cuando cxp ya tiene referencia_externa, retorna directo
    ing1.estado = IngestaBot.Estado.PROCESADO
    ing1.save(update_fields=["estado"])
    assert odoo_push.sincronizar(ing1).odoo_ref == "account.move:950"

    # 2. Odoo sin campos requeridos en account.move -> NoSincronizable legible
    cli_faltan = FakeCli(
        **{
            "res.partner:search": [810],
            "account.move:fields_get": {"move_type": {}, "partner_id": {}},
        }
    )
    odoo(cli_faltan)
    r2 = enviar(
        api,
        "gasto",
        {
            "proveedor": "Taller Oriente",
            "rif": "J-30111222-3",
            "fecha_emision": "2026-11-14",
            "monto_total": "15.00",
            "moneda": "USD",
        },
        key="ga-faltan",
    )
    ing2 = odoo_push.sincronizar(IngestaBot.objects.get(pk=r2.data["id_ingesta"]))
    assert ing2.estado == "PROCESADO" and "campos de factura esperados" in ing2.error

    # 3. Factura con solo RIF (sin nombre) cuando ese RIF no existe en Odoo -> pide el nombre
    odoo(FakeCli())
    bu = BotUsuario.objects.get(pk=bot_usuario.pk)
    ing_solo_rif = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu,
        kind=IngestaBot.Kind.FACTURA_PROVEEDOR,
        idempotency_key="fp-solo-rif",
        payload={
            "rif": "J-77665544-3",
            "numero_factura": "F-88",
            "fecha_emision": "2026-11-14",
            "monto_total": "20.00",
            "moneda": "USD",
        },
        fuente={"telegram_user_id": bu.telegram_user_id},
        estado=IngestaBot.Estado.PROCESADO,
        resultado={},
    )
    odoo_push.sincronizar(ing_solo_rif)
    assert "indica el nombre del proveedor" in ing_solo_rif.error


def test_diario_sin_config_se_autodetecta_si_es_unico(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    h = odoo(
        FakeCli(
            diarios=[
                {"id": 8, "currency_id": [1, "USD"]},
                {"id": 9, "currency_id": [2, "VEF"]},
            ]
        )
    )
    odoo_push.sincronizar(_pago(api))
    assert h["conn"].pagos[0]["journal_id"] == 8


def test_diario_ambiguo_pide_configurar(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    h = odoo(FakeCli(diarios=[{"id": 8, "currency_id": False}, {"id": 9, "currency_id": False}]))
    ing = _pago(api)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert h["conn"].pagos == [] and "diarios_pago" in ing.error


def test_pago_ve_con_alias_bs_usa_la_moneda_ves(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    h = odoo(FakeCli(), {"diarios_pago": {"default": 12}})
    odoo_push.sincronizar(_pago(api, moneda="Bs"))
    assert h["conn"].pagos[0]["moneda_id"] == 2


def test_cliente_del_pago_sin_odoo_no_se_crea(api, bot_usuario, empresa_a, odoo):  # noqa: F811
    Cliente.objects.create(id_empresa=empresa_a, razon_social="Taller", rif="J-123456789")
    h = odoo(FakeCli(), {"diarios_pago": {"default": 12}})
    ing = _pago(api)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert h["conn"].contactos == [] and h["conn"].pagos == [] and "no existe en Odoo" in ing.error


def test_pago_incompleto_no_se_empuja(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    h = odoo(FakeCli())
    ing = _pago(api, referencia=None)
    assert ing.estado == "INCOMPLETO"
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert h["conn"].pagos == [] and "Faltan datos" in ing.error


def test_pago_a_proveedor_es_outbound_y_anota_factura_si_existe(api, bot_usuario, odoo):  # noqa: F811
    h = odoo(
        FakeCli(**{"res.partner:search": [31], "account.move:search": [777]}),
        {"diarios_pago": {"default": 12}},
    )
    r = enviar(
        api,
        "pago_proveedor",
        {
            "proveedor": "Lubricantes SA",
            "monto": "900",
            "moneda": "USD",
            "factura_ref": "FAC-99",
        },
        key="pp",
    )
    ing = IngestaBot.objects.get(pk=r.data["id_ingesta"])
    odoo_push.sincronizar(ing)
    pago = h["conn"].pagos[0]
    assert pago["tipo"] == "proveedor" and pago["partner_id"] == 31
    assert "[account.move 777]" in pago["referencia"]


def test_proveedor_ambiguo_no_se_adivina(api, bot_usuario, odoo):  # noqa: F811
    h = odoo(
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
    assert h["conn"].pagos == [] and "ambiguo" in ing.error


def test_reintento_de_pago_reutiliza_el_existente_en_odoo(api, bot_usuario, cliente_odoo, odoo):  # noqa: F811
    h = odoo(
        FakeCli(**{"account.payment:search": [444]}),
        {"diarios_pago": {"default": 12}},
    )
    ing = _pago(api)
    odoo_push.sincronizar(ing)
    ing.refresh_from_db()
    assert h["conn"].pagos == [] and ing.odoo_ref == "account.payment:444"


def test_fallo_connector_error_anota_mensaje_generico_sin_filtrar_detalle(
    api, bot_usuario, catalogo, odoo, monkeypatch
):  # noqa: F811
    odoo(FakeCli())

    class Falla(FakeConn):
        def _get_client(self):
            raise ConnectorError("detalle interno sensible xmlrpc")

    monkeypatch.setattr(odoo_push, "OdooConnector", lambda inst: Falla(None))
    ing = odoo_push.sincronizar(_pedido_ingesta(api, catalogo))
    assert ing.estado == "PROCESADO"
    assert "sensible" not in ing.error
    assert "Odoo rechazó el envío" in ing.error


# ── disparo automático, endpoint y aislamiento multi-tenant ──────────────────


def test_tipos_sincronizables_se_encolan_al_confirmar(
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
            )  # incompleto -> no se encola
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
            enviar(
                api,
                "cotizacion",
                {"cliente": "Taller", "lineas": [{"producto": "Aceite 20W50", "cantidad": 1}]},
                key="e",
            )  # cotización es solo local -> no se encola
    assert enc.call_count == 3  # pedido + pago completo + contacto


def test_completar_pago_o_factura_lo_encola(
    api, bot_usuario, cliente_odoo, monedas_omni, django_capture_on_commit_callbacks
):  # noqa: F811
    ing = _pago(api, referencia=None)
    r_fac = enviar(
        api,
        "factura_proveedor",
        {"proveedor": "Prov Incompleto", "monto_total": "40", "moneda": "USD"},
        key="fp-inc",
    )
    ing_fac = IngestaBot.objects.get(pk=r_fac.data["id_ingesta"])
    assert ing_fac.estado == "INCOMPLETO"

    with patch("apps.bots_ingest.tasks.encolar_sync") as enc:
        with django_capture_on_commit_callbacks(execute=True):
            r1 = api.post(
                f"/api/bots/ingest/{ing.pk}/completar/",
                {"cambios": {"referencia": "R9"}},
                format="json",
            )
            r2 = api.post(
                f"/api/bots/ingest/{ing_fac.pk}/completar/",
                {
                    "cambios": {
                        "numero_factura": "F-100",
                        "fecha_emision": "2026-11-12",
                    }
                },
                format="json",
            )
    assert r1.status_code == 200 and r2.status_code == 200
    assert enc.call_count == 2


def test_endpoint_sincronizar(api, bot_usuario, catalogo, cliente_odoo):  # noqa: F811
    ing = _pedido_ingesta(api, catalogo)
    contacto = IngestaBot.objects.get(
        pk=enviar(
            api,
            "contacto",
            {
                "nombre": "P",
                "telefono": "04141234567",
                "ubicacion": {"latitud": 1, "longitud": 1},
            },
            key="z-ct",
        ).data["id_ingesta"]
    )
    with patch("apps.bots_ingest.tasks.encolar_sync") as enc:
        r = api.post(f"/api/bots/ingest/{ing.pk}/sincronizar/")
        r_ct = api.post(f"/api/bots/ingest/{contacto.pk}/sincronizar/")
        assert r.status_code == 202 and r_ct.status_code == 202 and enc.call_count == 2

    cotizacion = IngestaBot.objects.get(
        pk=enviar(
            api,
            "cotizacion",
            {"cliente": "Taller", "lineas": [{"producto": "Aceite 20W50", "cantidad": 1}]},
            key="z-cot",
        ).data["id_ingesta"]
    )
    assert api.post(f"/api/bots/ingest/{cotizacion.pk}/sincronizar/").status_code == 422
    IngestaBot.objects.filter(pk=ing.pk).update(estado="SINCRONIZADO")
    assert api.post(f"/api/bots/ingest/{ing.pk}/sincronizar/").status_code == 409
    inc = _pago(api, referencia=None, k="pg9")
    assert api.post(f"/api/bots/ingest/{inc.pk}/sincronizar/").status_code == 422


@pytest.mark.tenant
def test_aislamiento_tenant_en_sincronizacion_odoo(empresa_a, empresa_b, user_a, user_b, odoo):  # noqa: F811
    """Una ingesta de ``empresa_a`` jamás lee ni vincula proveedores/clientes de ``empresa_b``."""
    prov_b = Proveedor.objects.create(
        id_empresa=empresa_b,
        razon_social="Proveedor Ajeno B",
        rif="J-999999999",
        referencia_externa="9999",
    )
    bu_a = BotUsuario.objects.create(id_empresa=empresa_a, telegram_user_id=919191, usuario=user_a, nombre="Op A")
    # Incluso si resultado trajera el UUID de un proveedor de empresa_b, el filtro id_empresa lo ignora
    ing_a = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu_a,
        kind=IngestaBot.Kind.PROVEEDOR,
        idempotency_key="tenant-prov-a",
        payload={"nombre": "Proveedor Propio A", "rif": "J-888888888", "telefono": "04141112233"},
        fuente={"telegram_user_id": 919191},
        estado=IngestaBot.Estado.PROCESADO,
        resultado={"proveedor_id": str(prov_b.pk)},
    )
    creados = []
    cli = FakeCli(**{"res.partner:create": lambda args: creados.append(args[0]) or 333})
    odoo(cli)
    odoo_push.sincronizar(ing_a)
    ing_a.refresh_from_db()
    prov_b.refresh_from_db()
    assert ing_a.odoo_ref == "res.partner:333"
    assert prov_b.referencia_externa == "9999"
    assert creados[0]["name"] == "Proveedor Propio A"


# ── reglas aprendidas de CxC (producción) ────────────────────────────────────


@pytest.mark.parametrize(
    "codigo,esperado",
    [
        ("USD", 1),
        ("$", 1),
        ("usd", 1),
        ("VES", 2),
        ("Bs", 2),
        ("VEF", 2),
        ("VED", 2),
        ("EUR", None),
    ],
)
def test_moneda_usd_exacta_y_familia_bolivar(codigo, esperado):
    assert odoo_push._moneda_odoo(FakeCli(), codigo) == esperado


def test_vendedor_se_busca_por_login_o_email_y_no_se_adivina():
    una = FakeCli(**{"res.users:search": [4]})
    assert odoo_push._vendedor_odoo(una, "Ana@x.com") == 4
    dominio = una.llamadas[0][2][0]
    assert dominio[0] == "|" and ["email", "=ilike", "Ana@x.com"] in dominio
    assert odoo_push._vendedor_odoo(FakeCli(**{"res.users:search": [4, 5]}), "a@x.com") is None
    assert odoo_push._vendedor_odoo(FakeCli(**{"res.users:search": []}), "a@x.com") is None
    assert odoo_push._vendedor_odoo(FakeCli(), "") is None


def test_endurecimiento_rif_red_pagos_y_ramas_odoo_push(api, bot_usuario, monedas_omni, odoo, empresa_a):  # noqa: F811
    from apps.core.models import Contacto

    # 1. Paridad de _canon_rif y _variantes_rif (incluye formato l10n_ve con dígito verificador)
    assert odoo_push._canon_rif("j 29888777-1") == "J-298887771"
    assert odoo_push._canon_rif("PEND-12345678") is None
    assert odoo_push._canon_rif("   ") is None
    vars_rif = odoo_push._variantes_rif("J-123456789")
    assert "J-12345678-9" in vars_rif
    assert "123456789" in vars_rif
    assert odoo_push._variantes_rif("PEND-ABC") == []
    assert odoo_push._fecha_iso("no-es-fecha") is None

    # 2. _decimal_seguro rechaza montos corruptos / NaN con NoSincronizable
    with pytest.raises(odoo_push.NoSincronizable):
        odoo_push._decimal_seguro("100,00", "base_imponible")
    with pytest.raises(odoo_push.NoSincronizable):
        odoo_push._decimal_seguro("NaN", "monto")

    # 3. _crear_partner_borrador propaga OdooCallError cuando NO es de geolocalización
    cli_err = FakeCli(**{"res.partner:create": lambda _a: (_ for _ in ()).throw(OdooCallError("Permiso denegado"))})
    with pytest.raises(OdooCallError):
        odoo_push._crear_partner_borrador(cli_err, {"name": "X"}, lat="10.1", lon="-66.1")

    # 4. OdooCallError encadenado a TimeoutError / OSError se relanza como ErrorTransitorio
    def fallo_timeout(_args):
        try:
            raise TimeoutError("socket timed out")
        except TimeoutError as exc:
            raise OdooCallError("Error de red") from exc

    odoo(FakeCli(**{"res.partner:search": fallo_timeout}))
    r_ct = enviar(
        api,
        "contacto",
        {
            "nombre": "Red Caída",
            "telefono": "04141112233",
            "ubicacion": {"latitud": 10.0, "longitud": -66.0},
        },
        key="ct-net",
    )
    with pytest.raises(odoo_push.ErrorTransitorio):
        odoo_push.sincronizar(IngestaBot.objects.get(pk=r_ct.data["id_ingesta"]))

    # 5. Pago de cliente no existente en Omni resuelto en modo lectura en Odoo (por pedido_ref, RIF y nombre)
    pagos_legacy = []
    cli_legacy = FakeCli(
        **{
            "sale.order:search_read": [{"id": 10, "partner_id": [88, "Cliente Pedido"]}],
            "account.payment:fields_get": {"ref": {}, "amount": {}},
            "account.payment:create": lambda args: pagos_legacy.append(args[0]) or 991,
        }
    )
    odoo(cli_legacy, {"diarios_pago": {"default": 12}})
    bu = BotUsuario.objects.get(pk=bot_usuario.pk)
    ing_ped_ref = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu,
        kind=IngestaBot.Kind.PAGO,
        idempotency_key="pg-ped-ref",
        payload={
            "pedido_ref": "S00500",
            "monto": "50.00",
            "moneda": "USD",
            "referencia": "REF-500",
        },
        fuente={"telegram_user_id": bu.telegram_user_id},
        estado=IngestaBot.Estado.BORRADOR,
        resultado={},
    )
    odoo_push.sincronizar(ing_ped_ref)
    assert ing_ped_ref.odoo_ref == "account.payment:991"
    assert pagos_legacy[0]["partner_id"] == 88
    assert f"BOT-{ing_ped_ref.pk}" in pagos_legacy[0]["ref"]

    # Pago de cliente por nombre exacto y ambiguo + account.payment sin campo memo/ref + moneda inexistente
    cli_nom_pago = FakeCli(**{"res.partner:search": [89]})
    assert (
        odoo_push._partner_cliente_pago(
            None,
            cli_nom_pago,
            IngestaBot(
                id_empresa=empresa_a,
                payload={"cliente": "Comercial Norte"},
                resultado={},
            ),
        )
        == 89
    )
    with pytest.raises(odoo_push.NoSincronizable):
        odoo_push._partner_cliente_pago(
            None,
            FakeCli(**{"res.partner:search": [89, 90]}),
            IngestaBot(
                id_empresa=empresa_a,
                payload={"cliente": "Repetido"},
                resultado={},
            ),
        )
    with pytest.raises(odoo_push.NoSincronizable):
        odoo_push._campo_memo_pago(FakeCli(**{"account.payment:fields_get": {"amount": {}}}))

    odoo(FakeCli(), {"diarios_pago": {"default": 12}})
    ing_mon_pago = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu,
        kind=IngestaBot.Kind.PAGO,
        idempotency_key="pg-mon-err",
        payload={"rif": "J-112233445", "monto": "10", "moneda": "CAD", "referencia": "R"},
        fuente={"telegram_user_id": bu.telegram_user_id},
        estado=IngestaBot.Estado.BORRADOR,
        resultado={},
    )
    odoo(FakeCli(**{"res.partner:search": [45]}), {"diarios_pago": {"default": 12}})
    odoo_push.sincronizar(ing_mon_pago)
    assert "Moneda" in ing_mon_pago.error

    # 6. Ramas de proveedor en pagos, proveedor directo y documentos de compra
    contacto_gps = Contacto.objects.create(
        id_empresa=empresa_a,
        nombre="Prov Con Contacto GPS",
        latitud=Decimal("10.250000"),
        longitud=Decimal("-67.590000"),
    )
    prov_ref = Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Prov Ya Vinculado",
        rif="J-601112223",
        referencia_externa="654",
        contacto=contacto_gps,
    )
    assert (
        odoo_push._partner_proveedor_pago(
            FakeCli(),
            IngestaBot(
                id_empresa=empresa_a,
                payload={},
                resultado={"proveedor_id": str(prov_ref.pk)},
            ),
        )
        == 654
    )
    with pytest.raises(odoo_push.NoSincronizable):
        odoo_push._partner_proveedor_pago(
            FakeCli(),
            IngestaBot(id_empresa=empresa_a, payload={}, resultado={}),
        )

    # _push_proveedor: prov ya tiene referencia_externa, sin nombre, propio por marca y GPS desde prov.contacto
    ing_prov_ya = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu,
        kind=IngestaBot.Kind.PROVEEDOR,
        idempotency_key="prov-ya",
        payload={"nombre": "Prov Ya Vinculado", "rif": "J-601112223"},
        fuente={"telegram_user_id": bu.telegram_user_id},
        estado=IngestaBot.Estado.PROCESADO,
        resultado={"proveedor_id": str(prov_ref.pk)},
    )
    assert odoo_push.sincronizar(ing_prov_ya).odoo_ref == "res.partner:654"

    ing_sin_nom = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu,
        kind=IngestaBot.Kind.PROVEEDOR,
        idempotency_key="prov-sin-nom",
        payload={"rif": "J-609998887"},
        fuente={"telegram_user_id": bu.telegram_user_id},
        estado=IngestaBot.Estado.PROCESADO,
        resultado={},
    )
    odoo_push.sincronizar(ing_sin_nom)
    assert "no tiene nombre" in ing_sin_nom.error

    prov_gps = Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Prov GPS Contacto",
        rif="J-602223334",
        contacto=Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Prov GPS Contacto",
            latitud=Decimal("10.330000"),
            longitud=Decimal("-67.110000"),
        ),
    )
    creados_gps = []
    odoo(FakeCli(**{"res.partner:create": lambda args: creados_gps.append(args[0]) or 777}))
    ing_prov_gps = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu,
        kind=IngestaBot.Kind.PROVEEDOR,
        idempotency_key="prov-gps-contacto",
        payload={"nombre": "Prov GPS Contacto", "rif": "J-602223334"},
        fuente={"telegram_user_id": bu.telegram_user_id},
        estado=IngestaBot.Estado.PROCESADO,
        resultado={"proveedor_id": str(prov_gps.pk)},
    )
    odoo_push.sincronizar(ing_prov_gps)
    assert creados_gps[0]["partner_latitude"] == pytest.approx(10.33)

    # _resolver_o_crear_proveedor_documento: sin rif ni nombre, ambiguo por nombre, match por nombre y moneda inválida
    with pytest.raises(odoo_push.NoSincronizable):
        odoo_push._resolver_o_crear_proveedor_documento(
            IngestaBot(id_empresa=empresa_a, payload={}, resultado={}),
            FakeCli(),
            "BOT-X",
        )
    with pytest.raises(odoo_push.NoSincronizable):
        odoo_push._resolver_o_crear_proveedor_documento(
            IngestaBot(
                id_empresa=empresa_a,
                payload={"proveedor": "Ambiguo"},
                resultado={},
            ),
            FakeCli(**{"res.partner:search": lambda args: ([1, 2] if args[0] and args[0][0][0] == "name" else [])}),
            "BOT-X",
        )
    pid_unico, creado_unico = odoo_push._resolver_o_crear_proveedor_documento(
        IngestaBot(
            id_empresa=empresa_a,
            payload={"proveedor": "Existente Único"},
            resultado={},
        ),
        FakeCli(**{"res.partner:search": lambda args: ([512] if args[0] and args[0][0][0] == "name" else [])}),
        "BOT-X",
    )
    assert (pid_unico, creado_unico) == (512, False)

    odoo(FakeCli(**{"res.partner:search": lambda args: ([512] if args[0] and args[0][0][0] == "name" else [])}))
    ing_doc_mon = IngestaBot.objects.create(
        id_empresa=empresa_a,
        bot_usuario=bu,
        kind=IngestaBot.Kind.GASTO,
        idempotency_key="ga-mon-err",
        payload={
            "proveedor": "Existente Único",
            "fecha_emision": "2026-11-15",
            "monto_total": "12.00",
            "moneda": "CHF",
        },
        fuente={"telegram_user_id": bu.telegram_user_id},
        estado=IngestaBot.Estado.PROCESADO,
        resultado={},
    )
    odoo_push.sincronizar(ing_doc_mon)
    assert "Moneda" in ing_doc_mon.error
