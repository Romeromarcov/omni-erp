"""Lector Odoo → espejo CxC Lubrikca (Fase 5, SOLO LECTURA).

Porta el mapeo de campos probado contra el Odoo 18 QA de Lubrikca (ver
``CxC_Lubrikca/docs/ODOO_MAPEO.md`` y ``docs/cxc-lubrikca/MAPA_DATOS_GAPS.md``):

  - SO identificada por ``name`` (S00553), no por id numérico.
  - ``vendedor_email`` = ``user_id.login`` (resuelto con 2ª consulta a res.users).
  - ``fecha_entrega`` = ``stock.picking.date_done`` del despacho saliente.
  - ``estado_entrega`` = ``sale.order.delivery_status`` (full/partial/pending).
  - ``entregada_completa`` = delivery_status == "full".
  - ``tiene_devolucion`` = picking con ``return_id`` seteado.
  - ``cantidad_entregada`` = ``sale.order.line.qty_delivered`` (ya neta de devoluciones).
  - marca/categoría salen del PRODUCTO (``brand_id`` / raíz de ``categ_id``).
  - ``metodo_pago`` = ``journal_id`` (el diario lleva la identidad real).
  - ``es_primera_compra`` se calcula (primera SO del partner, search_count == 1).
  - ``monto_facturado`` = suma de ``amount_total_signed_usd`` de out_invoice posted.
  - ``ncs_facturadas`` = suma de ``amount_total_signed_usd`` de out_refund posted.

Aislamiento (regla inviolable de la fase): este módulo NUNCA escribe a Odoo.
Solo invoca ``search_read``, ``read`` y ``search_count``. Reutiliza el cliente
del núcleo (``integration_hub``) por composición, sin editarlo.

Diseño testeable: ``LubrikcaOdooReader`` recibe un ``execute`` inyectable con
firma ``execute(model, method, args, kwargs)`` — idéntica a
``OdooXMLRPCClient.call``. En tests se prueba con un ``execute`` falso que
despacha por (modelo, método), sin red.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

ExecuteFn = Callable[[str, str, list, dict], Any]

# Modelos Odoo consultados (solo lectura).
MODEL_ORDEN = "sale.order"
MODEL_LINEA = "sale.order.line"
MODEL_PAGO = "account.payment"
MODEL_PICKING = "stock.picking"
MODEL_PRODUCT = "product.product"
MODEL_MOVE = "account.move"
MODEL_USERS = "res.users"

ODOO_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

# Fallback de marca cuando el producto no tiene brand_id (la gran mayoría: 🚩).
MARCA_FALLBACK = "*"


# --- helpers de normalización Odoo -----------------------------------------
def _m2o_id(value: Any) -> str:
    """Odoo devuelve many2one como ``[id, "nombre"]`` o ``False``."""
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    if value in (False, None):
        return ""
    return str(value)


def _m2o_name(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return str(value[1])
    if value in (False, None):
        return ""
    return str(value)


def _dec(value: Any) -> Decimal:
    """Convierte a Decimal vía str() (R-CODE-4: nunca float)."""
    if value in (False, None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _date_str(value: Any) -> str | None:
    if value in (False, None, ""):
        return None
    return str(value)[:10]


def _datetime_str(value: Any) -> str | None:
    if value in (False, None, ""):
        return None
    return str(value)[:19]


class LubrikcaOdooReader:
    """Lector solo-lectura del Odoo de Lubrikca hacia el espejo.

    Toda la red entra por ``self._execute`` (inyectado). No hay estado mutable.
    """

    def __init__(self, execute: ExecuteFn) -> None:
        self._execute = execute

    # --- primitivas (solo lectura) -----------------------------------------
    def _search_read(
        self, model: str, domain: list, fields: list[str], **kwargs: Any
    ) -> list[dict]:
        opts: dict[str, Any] = {"fields": fields}
        opts.update(kwargs)
        result = self._execute(model, "search_read", [domain], opts)
        return result or []

    def _read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        if not ids:
            return []
        result = self._execute(model, "read", [ids], {"fields": fields})
        return result or []

    def _search_count(self, model: str, domain: list) -> int:
        return int(self._execute(model, "search_count", [domain], {}) or 0)

    # --- resolución de relaciones ------------------------------------------
    def _user_logins(self, user_ids: set[int]) -> dict[int, str]:
        recs = self._read(MODEL_USERS, sorted(user_ids), ["id", "login"])
        return {int(r["id"]): str(r.get("login", "") or "") for r in recs}

    # --- 1. Pedidos --------------------------------------------------------
    def leer_pedidos(self, desde: Any = None, limite: int = 200) -> list[dict]:
        """Lee sale.order y devuelve dicts ya enriquecidos para el espejo.

        Campos: so_id, cliente_externo_id, fecha, monto_total, lista_precios,
        vendedor_email, es_primera_compra, delivery_status, invoice_status, state.
        """
        domain: list = []
        if desde:
            domain.append(["write_date", ">", str(desde)])
        recs = self._search_read(
            MODEL_ORDEN,
            domain,
            [
                "id", "name", "partner_id", "date_order", "amount_total",
                "pricelist_id", "user_id", "delivery_status", "invoice_status",
                "state",
            ],
            limit=limite,
        )
        if not recs:
            return []

        uids = {int(_m2o_id(r.get("user_id"))) for r in recs if _m2o_id(r.get("user_id"))}
        logins = self._user_logins(uids)

        out: list[dict] = []
        for r in recs:
            uid = _m2o_id(r.get("user_id"))
            partner_id = _m2o_id(r.get("partner_id"))
            es_primera = False
            if partner_id:
                cnt = self._search_count(
                    MODEL_ORDEN, [["partner_id", "=", int(partner_id)]]
                )
                es_primera = cnt == 1
            out.append(
                {
                    "so_id": str(r.get("name", "")),
                    "cliente_externo_id": partner_id,
                    "fecha": _date_str(r.get("date_order")),
                    "monto_total": _dec(r.get("amount_total")),
                    "lista_precios": _m2o_id(r.get("pricelist_id")),
                    "vendedor_email": logins.get(int(uid), "") if uid else "",
                    "es_primera_compra": es_primera,
                    "estado_entrega": str(r.get("delivery_status", "") or ""),
                    "invoice_status": str(r.get("invoice_status", "") or ""),
                    "state": str(r.get("state", "") or ""),
                }
            )
        return out

    # --- 2. Líneas ---------------------------------------------------------
    def leer_lineas(self, so_names: list[str]) -> list[dict]:
        """Lee sale.order.line de las SO indicadas (por nombre).

        marca = brand_id name del producto (fallback "*"); categoria = raíz del
        árbol categ_id (Comercial/Industrial); cantidad_entregada = qty_delivered.
        """
        if not so_names:
            return []
        domain = [["order_id.name", "in", list(so_names)], ["display_type", "=", False]]
        recs = self._search_read(
            MODEL_LINEA,
            domain,
            [
                "id", "order_id", "product_id", "product_uom_qty", "price_unit",
                "qty_delivered",
            ],
        )
        if not recs:
            return []

        prod_ids = {
            int(_m2o_id(r.get("product_id")))
            for r in recs
            if _m2o_id(r.get("product_id"))
        }
        productos = self._productos(prod_ids)

        out: list[dict] = []
        for r in recs:
            pid = _m2o_id(r.get("product_id"))
            marca, categoria = productos.get(int(pid), (MARCA_FALLBACK, "*")) if pid else (
                MARCA_FALLBACK,
                "*",
            )
            out.append(
                {
                    "linea_id": str(r.get("id", "")),
                    "so_id": _m2o_name(r.get("order_id")),
                    "producto": _m2o_name(r.get("product_id")) or _m2o_id(r.get("product_id")),
                    "marca": marca,
                    "categoria": categoria,
                    "cantidad": _dec(r.get("product_uom_qty")),
                    "precio_unitario": _dec(r.get("price_unit")),
                    "cantidad_entregada": _dec(r.get("qty_delivered")),
                }
            )
        return out

    def _productos(self, prod_ids: set[int]) -> dict[int, tuple[str, str]]:
        """Mapa producto → (marca, categoría raíz).

        Marca: ``brand_id`` name; fallback "*" cuando vacío (la mayoría de los
        productos de Lubrikca no tienen marca). Categoría: raíz del árbol —
        ``categ_id`` viene como "Comercial / Lubricantes"; tomamos el 1er nivel.
        """
        recs = self._read(MODEL_PRODUCT, sorted(prod_ids), ["id", "brand_id", "categ_id"])
        out: dict[int, tuple[str, str]] = {}
        for r in recs:
            marca = _m2o_name(r.get("brand_id")).strip() or MARCA_FALLBACK
            categoria_full = _m2o_name(r.get("categ_id"))
            # Odoo separa el árbol con " / "; la raíz es el primer segmento.
            categoria = categoria_full.split("/")[0].strip() if categoria_full else "*"
            if not categoria:
                categoria = "*"
            out[int(r["id"])] = (marca, categoria)
        return out

    # --- 3. Entregas (pickings) -------------------------------------------
    def leer_entregas(self, so_names: list[str]) -> dict[str, dict]:
        """Mapa SO name → datos de entrega derivados de stock.picking outgoing.

        - fecha_entrega = date_done más reciente del despacho saliente.
        - estado_entrega: se rellena desde el pedido (delivery_status); aquí se
          deriva ``entregada_completa`` cuando el picking está done.
        - tiene_devolucion: existe un picking con ``return_id`` seteado.
        La cantidad neta entregada se toma de la línea (qty_delivered ya es neta).
        """
        if not so_names:
            return {}
        recs = self._search_read(
            MODEL_PICKING,
            [
                ["sale_id.name", "in", list(so_names)],
                ["picking_type_code", "=", "outgoing"],
            ],
            ["sale_id", "date_done", "scheduled_date", "state", "return_id"],
        )
        out: dict[str, dict] = {}
        for p in recs:
            so = _m2o_name(p.get("sale_id"))
            if not so:
                continue
            info = out.setdefault(
                so,
                {
                    "fecha_entrega": None,
                    "entregada_completa": False,
                    "tiene_devolucion": False,
                },
            )
            fecha = _date_str(p.get("date_done")) or _date_str(p.get("scheduled_date"))
            if fecha and (info["fecha_entrega"] is None or fecha > info["fecha_entrega"]):
                info["fecha_entrega"] = fecha
            if str(p.get("state", "")) == "done":
                info["entregada_completa"] = True
            if _m2o_id(p.get("return_id")):
                info["tiene_devolucion"] = True
        return out

    # --- 4. Pagos ----------------------------------------------------------
    def leer_pagos(self, desde: Any = None, limite: int = 300) -> list[dict]:
        """Lee account.payment inbound (cobros a clientes)."""
        domain: list = [["payment_type", "=", "inbound"]]
        if desde:
            domain.append(["write_date", ">", str(desde)])
        recs = self._search_read(
            MODEL_PAGO,
            domain,
            ["id", "partner_id", "amount", "currency_id", "journal_id", "date"],
            limit=limite,
        )
        if not recs:
            return []

        # vendedor_email vía partner.user_id.login (2 saltos).
        partner_ids = {
            int(_m2o_id(r.get("partner_id")))
            for r in recs
            if _m2o_id(r.get("partner_id"))
        }
        vendedores = self._vendedor_por_partner(partner_ids)

        out: list[dict] = []
        for r in recs:
            moneda = "USD" if _m2o_name(r.get("currency_id")) == "USD" else "VES"
            pid = _m2o_id(r.get("partner_id"))
            out.append(
                {
                    "pago_id": str(r.get("id", "")),
                    "cliente_externo_id": pid,
                    "monto": _dec(r.get("amount")),
                    "moneda": moneda,
                    "metodo_pago": _m2o_id(r.get("journal_id")),
                    "fecha_pago": _datetime_str(r.get("date")),
                    "vendedor_email": vendedores.get(int(pid), "") if pid else "",
                }
            )
        return out

    def _vendedor_por_partner(self, partner_ids: set[int]) -> dict[int, str]:
        if not partner_ids:
            return {}
        partners = self._read("res.partner", sorted(partner_ids), ["id", "user_id"])
        uids = {
            int(_m2o_id(p.get("user_id")))
            for p in partners
            if _m2o_id(p.get("user_id"))
        }
        logins = self._user_logins(uids)
        out: dict[int, str] = {}
        for p in partners:
            uid = _m2o_id(p.get("user_id"))
            out[int(p["id"])] = logins.get(int(uid), "") if uid else ""
        return out

    # --- 5. Facturas (conciliación) ---------------------------------------
    def leer_facturas(self, so_names: list[str]) -> dict[str, dict]:
        """Mapa SO name → {monto_facturado_usd, ncs, factura_id}.

        - monto_facturado = suma de ``amount_total_signed_usd`` de out_invoice.
        - ncs = suma de ``amount_total_signed_usd`` de out_refund (notas crédito).
        Solo posted; ligadas por ``invoice_origin = SO.name``. La compañía
        factura en VES pero ``amount_total_signed_usd`` da el equivalente USD a
        la tasa registrada en la factura (gap #15 del MAPA_DATOS_GAPS).
        """
        if not so_names:
            return {}
        recs = self._search_read(
            MODEL_MOVE,
            [
                ["invoice_origin", "in", list(so_names)],
                ["move_type", "in", ["out_invoice", "out_refund"]],
                ["state", "=", "posted"],
            ],
            ["id", "invoice_origin", "move_type", "amount_total_signed_usd"],
        )
        out: dict[str, dict] = {}
        for r in recs:
            so = str(r.get("invoice_origin", "") or "")
            if not so:
                continue
            info = out.setdefault(
                so,
                {
                    "monto_facturado_usd": Decimal("0"),
                    "ncs": Decimal("0"),
                    "factura_id": "",
                },
            )
            usd = abs(_dec(r.get("amount_total_signed_usd")))
            if str(r.get("move_type", "")) == "out_refund":
                info["ncs"] += usd
            else:
                info["monto_facturado_usd"] += usd
                if not info["factura_id"]:
                    info["factura_id"] = str(r.get("id", ""))
        return out


# --- Fábrica de productor (plumbing fino, reúsa el núcleo) ------------------
def execute_para_empresa(empresa) -> ExecuteFn:
    """Devuelve un ``execute`` ligado al conector Odoo activo de la empresa.

    Reúsa ``integration_hub`` por composición: localiza la ``ConectorInstancia``
    Odoo activa de la empresa, construye el conector vía el registry y devuelve
    ``client.call``. Lectura pura; lanza error claro si no hay conector.
    """
    from apps.integration_hub.connectors.registry import registry
    from apps.integration_hub.models import ConectorInstancia

    instancia = (
        ConectorInstancia.objects.select_related("id_proveedor", "id_empresa")
        .filter(id_empresa=empresa, id_proveedor__codigo="odoo", activo=True)
        .order_by("-fecha_actualizacion")
        .first()
    )
    if instancia is None:
        from apps.cxc_lubrikca.services.sync import SyncError

        raise SyncError(
            f"La empresa {getattr(empresa, 'pk', empresa)} no tiene un conector "
            "Odoo activo. Configúralo primero (configurar_conector_odoo)."
        )

    connector = registry.get_connector(instancia)
    client = connector._get_client()
    return client.call
