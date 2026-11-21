"""
OdooXMLRPCClient — Cliente XML-RPC para Odoo (todas las versiones).

Soporta Odoo 8 a 18+ mediante el protocolo XML-RPC estándar.
Compatible con Odoo Community, Enterprise, y SaaS.

Adaptado y extendido del cliente en GestionCxC para uso multi-tenant
dentro del Integration Hub de Omni ERP.

Seguridad (R-CODE-8):
  - Las credenciales NUNCA se loguean.
  - Las contraseñas/api_keys se enmascaran en mensajes de error.
  - El constructor lanza OdooAuthError si las credenciales son inválidas.
"""

from __future__ import annotations

import logging
import xmlrpc.client  # nosec B411
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

# B411: endurecer xmlrpc contra ataques XML (billion laughs, entidades externas)
# en las respuestas del servidor Odoo externo. monkey_patch() sustituye el parser
# de xmlrpclib por el de defusedxml a nivel de proceso (idempotente).
from defusedxml.xmlrpc import monkey_patch as _defuse_xmlrpc

_defuse_xmlrpc()

logger = logging.getLogger(__name__)


def normalize_odoo_host(raw: str) -> str:
    """
    Normaliza la URL base de un servidor Odoo a ``esquema://host[:puerto]``.

    Es muy común que el usuario pegue la URL del navegador (la página de login,
    ej. ``https://miempresa.odoo.com/en/web/login``) en el campo Host. Eso
    rompía el XML-RPC porque los endpoints se construyen como
    ``{host}/xmlrpc/2/common`` → ``.../en/web/login/xmlrpc/2/common`` (ruta
    inválida; el servidor responde HTML y xmlrpc lanza ResponseNotReady).

    Esta función descarta cualquier ruta, query o fragmento y conserva solo
    el esquema y el dominio (con puerto si lo hay). Si falta el esquema, asume
    ``https://``.

    Ejemplos:
        "miempresa.odoo.com/en/web/login"     → "https://miempresa.odoo.com"
        "https://x.odoo.com/web/login?foo=1"  → "https://x.odoo.com"
        "http://localhost:8069/web"           → "http://localhost:8069"
    """
    base = (raw or "").strip()
    if not base:
        return ""
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    parts = urlsplit(base)
    if not parts.netloc:
        # urlsplit no pudo identificar el dominio; devolvemos lo saneado mínimo.
        return base.rstrip("/")
    return f"{parts.scheme}://{parts.netloc}"


class OdooAuthError(Exception):
    """Autenticación fallida con Odoo."""


class OdooCallError(Exception):
    """Error al ejecutar un método en Odoo."""


class OdooXMLRPCClient:
    """
    Cliente XML-RPC para Odoo multi-versión.

    Parámetros:
        host (str): URL base, ej: "miodoo.odoo.com" o "http://localhost:8069"
        db (str): nombre de la base de datos Odoo
        user (str): email o login del usuario
        api_key (str): API key o contraseña del usuario
        timeout (int): timeout en segundos para llamadas XML-RPC (default 30)

    Ejemplo:
        client = OdooXMLRPCClient("miodoo.odoo.com", "mi_db", "admin@co.com", "key123")
        ventas = client.call("sale.order", "search_read", [[["state", "=", "sale"]]])
    """

    def __init__(
        self,
        host: str,
        db: str,
        user: str,
        api_key: str,
        timeout: int = 30,
    ):
        # Normaliza el host a esquema://dominio, tolerando que el usuario pegue
        # la URL del navegador (p. ej. .../web/login) — ver normalize_odoo_host.
        self._host = normalize_odoo_host(host)
        self._db = db.strip()
        self._user = user.strip()
        self._api_key = api_key  # No loguear
        self._timeout = timeout

        self._common_url = f"{self._host}/xmlrpc/2/common"
        self._object_url = f"{self._host}/xmlrpc/2/object"

        self.uid: int | None = None
        self._version_info: dict = {}
        self._models: xmlrpc.client.ServerProxy | None = None
        self._fields_cache: dict[str, set[str]] = {}

        self._authenticate()

    def _authenticate(self):
        """Autentica contra Odoo y almacena el UID."""
        try:
            common = xmlrpc.client.ServerProxy(
                self._common_url,
                allow_none=True,
            )
            # Obtener versión (no requiere autenticación)
            try:
                self._version_info = common.version() or {}
            except Exception:
                self._version_info = {}

            uid = common.authenticate(self._db, self._user, self._api_key, {})
            if not uid:
                raise OdooAuthError(
                    f"Autenticación Odoo fallida para usuario '{self._user}' "
                    f"en '{self._host}' (db: '{self._db}'). "
                    "Verifique las credenciales."
                )
            self.uid = uid
            self._models = xmlrpc.client.ServerProxy(
                self._object_url,
                allow_none=True,
            )
            logger.info(
                "OdooXMLRPCClient: conectado a %s (uid=%s, versión=%s)",
                self._host,
                uid,
                self._version_info.get("server_version", "?"),
            )
        except OdooAuthError:
            raise
        except Exception as exc:
            # No propagar la excepción original que podría tener la api_key
            raise OdooAuthError(f"Error de conexión con Odoo en '{self._host}': {type(exc).__name__}") from None

    def call(
        self,
        model: str,
        method: str,
        domain: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        """
        Ejecuta un método en un modelo de Odoo vía XML-RPC.

        Args:
            model: nombre del modelo Odoo, ej: "sale.order"
            method: nombre del método, ej: "search_read", "read", "write", "create"
            domain: lista de argumentos posicionales (domain para search_read, IDs para read, etc.)
            kwargs: argumentos con nombre (fields, limit, offset, etc.)

        Returns:
            El resultado del método Odoo (list, dict, int, bool, etc.)

        Raises:
            OdooCallError: si el llamado falla en Odoo
        """
        try:
            result = self._models.execute_kw(
                self._db,
                self.uid,
                self._api_key,
                model,
                method,
                domain if domain is not None else [[]],
                kwargs or {},
            )
            return result
        except xmlrpc.client.Fault as fault:
            raise OdooCallError(f"Odoo fault en {model}.{method}: {fault.faultCode} — {fault.faultString}") from fault
        except Exception as exc:
            raise OdooCallError(f"Error en {model}.{method}: {type(exc).__name__}: {exc}") from exc

    def get_version(self) -> dict:
        """Retorna información de versión detectada al autenticar."""
        return self._version_info

    def _get_model_fields(self, modelo: str) -> set[str]:
        """Retorna campos disponibles en ``modelo`` (cacheados por instancia)."""
        cache = getattr(self, "_fields_cache", None)
        if cache is None:
            cache = {}
            self._fields_cache = cache
        if modelo in cache:
            return cache[modelo]

        campos: set[str] = set()
        try:
            resp = self.call(modelo, "fields_get", [[]], {"attributes": ["string"]})
            if isinstance(resp, dict):
                campos = {str(k) for k in resp.keys()}
        except (OdooCallError, KeyError, AttributeError, TypeError):
            campos = set()
        cache[modelo] = campos
        return campos

    def _campos_disponibles(
        self,
        modelo: str,
        base_fields: list[str],
        opcionales: tuple[str, ...],
        fallback: list[str],
    ) -> list[str]:
        """Filtra ``base_fields + opcionales`` contra los campos reales de ``modelo``."""
        campos_modelo = self._get_model_fields(modelo)
        if not campos_modelo:
            return list(fallback)
        if "id" in campos_modelo:
            return [f for f in (*base_fields, *opcionales) if f in campos_modelo]
        return [*base_fields, *(f for f in opcionales if f in campos_modelo)]

    @staticmethod
    def _m2o_id(val: Any) -> int | None:
        if isinstance(val, (list, tuple)) and val:
            raw_id = val[0]
        else:
            raw_id = val
        if isinstance(raw_id, bool) or raw_id in (None, "", 0):
            return None
        try:
            parsed = int(raw_id)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _m2o_name(val: Any) -> str:
        if isinstance(val, (list, tuple)) and len(val) > 1 and val[1]:
            return str(val[1])
        return ""

    @staticmethod
    def _to_decimal(val: Any) -> Decimal:
        if val in (None, "", False):
            return Decimal("0")
        try:
            return Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    # ── Ping / health ─────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Verifica que la conexión siga activa."""
        try:
            self.call("res.lang", "search_count", [[]])
            return True
        except Exception:
            return False

    # ── Socios / Contactos ────────────────────────────────────────────────────

    def get_socios(
        self,
        cliente: bool | None = None,
        proveedor: bool | None = None,
        desde: str | None = None,
        limite: int = 500,
    ) -> list[dict]:
        """
        Trae socios (res.partner) con criterios opcionales.

        Args:
            cliente: True = solo clientes, None = todos
            proveedor: True = solo proveedores, None = todos
            desde: fecha ISO "YYYY-MM-DD" para filtrar por write_date
            limite: máximo de registros a retornar
        """
        domain: list = [["active", "=", True]]
        if cliente is True:
            domain.append(["customer_rank", ">", 0])
        if proveedor is True:
            domain.append(["supplier_rank", ">", 0])
        if desde:
            domain.append(["write_date", ">=", desde])

        return self.call(
            "res.partner",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "email",
                    "phone",
                    "mobile",
                    "street",
                    "city",
                    "country_id",
                    "state_id",
                    "vat",  # número fiscal
                    "customer_rank",
                    "supplier_rank",
                    "company_type",  # person | company
                    "parent_id",  # empresa padre si es contacto
                    "website",
                    "comment",
                    "write_date",
                    "create_date",
                    "active",
                ],
                "limit": limite,
            },
        )

    def buscar_socio(self, query: str, limite: int = 15) -> list[dict]:
        """Búsqueda incremental de socios por nombre."""
        return self.call(
            "res.partner",
            "search_read",
            [[["name", "ilike", query], ["active", "=", True]]],
            {
                "fields": [
                    "id",
                    "name",
                    "email",
                    "phone",
                    "vat",
                    "customer_rank",
                    "supplier_rank",
                ],
                "limit": limite,
            },
        )

    # ── Productos ─────────────────────────────────────────────────────────────

    def get_productos(self, desde: str | None = None, limite: int = 500) -> list[dict]:
        """Productos activos (product.template)."""
        domain: list = [["active", "=", True]]
        if desde:
            domain.append(["write_date", ">=", desde])
        return self.call(
            "product.template",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "default_code",
                    "description_sale",
                    "list_price",
                    "standard_price",
                    "categ_id",
                    "uom_id",
                    "uom_po_id",
                    "type",  # consu | service | product
                    "sale_ok",
                    "purchase_ok",
                    "active",
                    "barcode",
                    "weight",
                    "volume",
                    "write_date",
                    "create_date",
                ],
                "limit": limite,
            },
        )

    def get_variantes_producto(self, tmpl_id: int) -> list[dict]:
        """Variantes de un product.template."""
        return self.call(
            "product.product",
            "search_read",
            [[["product_tmpl_id", "=", tmpl_id], ["active", "=", True]]],
            {
                "fields": [
                    "id",
                    "name",
                    "default_code",
                    "barcode",
                    "product_template_attribute_value_ids",
                ],
                "limit": 100,
            },
        )

    # ── Ventas ────────────────────────────────────────────────────────────────

    def get_pedidos_venta(
        self,
        solo_confirmadas: bool = True,
        desde: str | None = None,
        limite: int = 200,
    ) -> list[dict]:
        """Pedidos de venta (sale.order)."""
        states = ["sale", "done"] if solo_confirmadas else ["draft", "sent", "sale", "done"]
        domain: list = [["state", "in", states]]
        if desde:
            domain.append(["write_date", ">=", desde])
        return self.call(
            "sale.order",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "partner_id",
                    "user_id",
                    "date_order",
                    "state",
                    "invoice_status",
                    "amount_untaxed",
                    "amount_tax",
                    "amount_total",
                    "currency_id",
                    "pricelist_id",
                    "payment_term_id",
                    "write_date",
                    "create_date",
                ],
                "limit": limite,
                "order": "date_order desc",
            },
        )

    def get_lineas_pedido_venta(self, order_id: int) -> list[dict]:
        """Líneas de un pedido de venta."""
        return self.call(
            "sale.order.line",
            "search_read",
            [[["order_id", "=", order_id]]],
            {
                "fields": [
                    "id",
                    "product_id",
                    "product_uom_qty",
                    "price_unit",
                    "discount",
                    "price_subtotal",
                    "price_tax",
                    "price_total",
                    "tax_id",
                ]
            },
        )

    # ── Compras ───────────────────────────────────────────────────────────────

    def get_pedidos_compra(
        self,
        desde: str | None = None,
        limite: int = 200,
    ) -> list[dict]:
        """Órdenes de compra confirmadas (purchase.order)."""
        domain: list = [["state", "in", ["purchase", "done"]]]
        if desde:
            domain.append(["write_date", ">=", desde])
        return self.call(
            "purchase.order",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "partner_id",
                    "user_id",
                    "date_order",
                    "date_approve",
                    "state",
                    "invoice_status",
                    "invoice_ids",
                    "amount_untaxed",
                    "amount_tax",
                    "amount_total",
                    "currency_id",
                    "write_date",
                    "create_date",
                ],
                "limit": limite,
                "order": "date_order desc",
            },
        )

    def get_lineas_pedido_compra(self, order_id: int) -> list[dict]:
        """Líneas de una orden de compra."""
        return self.call(
            "purchase.order.line",
            "search_read",
            [[["order_id", "=", order_id]]],
            {
                "fields": [
                    "id",
                    "product_id",
                    "product_qty",
                    "price_unit",
                    "price_subtotal",
                    "taxes_id",
                    "qty_invoiced",
                    "qty_received",
                ]
            },
        )

    # ── Facturas ──────────────────────────────────────────────────────────────

    def get_facturas(
        self,
        tipo: str = "out_invoice",
        desde: str | None = None,
        limite: int = 200,
    ) -> list[dict]:
        """
        Facturas (account.move).

        Args:
            tipo: "out_invoice" (cliente), "in_invoice" (proveedor),
                  "out_refund" (nota crédito cliente), "in_refund" (nota crédito proveedor)
        """
        domain: list = [["move_type", "=", tipo], ["state", "=", "posted"]]
        if desde:
            domain.append(["write_date", ">=", desde])
        return self.call(
            "account.move",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "partner_id",
                    "invoice_origin",
                    "invoice_date",
                    "invoice_date_due",
                    "amount_untaxed",
                    "amount_tax",
                    "amount_total",
                    "amount_residual",
                    "currency_id",
                    "payment_state",
                    "state",
                    "move_type",
                    "ref",
                    "write_date",
                    "create_date",
                ],
                "limit": limite,
                "order": "invoice_date desc",
            },
        )

    def get_lineas_factura(self, move_id: int) -> list[dict]:
        """
        Líneas de producto de una factura (account.move.line).

        Filtra a líneas reales de producto: excluye secciones/notas
        (``display_type``) y líneas sin producto (impuesto, término de pago).
        """
        return self.call(
            "account.move.line",
            "search_read",
            [
                [
                    ["move_id", "=", move_id],
                    ["display_type", "=", False],
                    ["product_id", "!=", False],
                ]
            ],
            {
                "fields": [
                    "id",
                    "product_id",
                    "quantity",
                    "price_unit",
                    "discount",
                    "price_subtotal",
                    "price_total",
                    "tax_ids",
                ]
            },
        )

    # ── Pagos ─────────────────────────────────────────────────────────────────

    def get_pagos(
        self,
        tipo: str | None = None,
        desde: str | None = None,
        limite: int = 300,
    ) -> list[dict]:
        """
        Pagos (account.payment).

        Args:
            tipo: "inbound" (cobros a clientes), "outbound" (pagos a proveedores), None = todos
        """
        domain: list = [["state", "in", ["in_process", "paid", "posted"]]]
        if tipo:
            domain.append(["payment_type", "=", tipo])
        if desde:
            domain.append(["date", ">=", desde])

        base_fields = [
            "id",
            "name",
            "partner_id",
            "payment_type",
            "partner_type",
            "amount",
            "date",
            "state",
            "journal_id",
            "currency_id",
            "reconciled_invoice_ids",
            "write_date",
            "create_date",
        ]
        fields = self._campos_disponibles(
            "account.payment",
            base_fields,
            ("memo", "payment_reference", "ref", "move_id", "reconciled_bill_ids"),
            # Fallback estándar compatible con Odoo 18+ (sin 'ref', removido en Odoo 18).
            [*base_fields, "memo", "payment_reference", "move_id", "reconciled_bill_ids"],
        )

        return self.call(
            "account.payment",
            "search_read",
            [domain],
            {
                "fields": fields,
                "limit": limite,
                "order": "date desc",
            },
        )

    def get_reconciliaciones_pagos(self, move_ids: list[int]) -> dict[int, list[dict]]:
        """Lee reconciliaciones parciales en lote para los ``move_id`` de ``account.payment``.

        Ejecuta a lo sumo 4 lecturas XML-RPC en lote (cero N+1):
          1. ``account.move.line`` (líneas CxC/CxP de los asientos de pago).
          2. ``account.partial.reconcile`` (montos y monedas conciliadas).
          3. ``account.move.line`` (líneas contraparte de facturas/notas).
          4. ``account.move`` (``move_type``, ``name``, ``currency_id`` de contrapartes).
        """
        ids_limpios = sorted({int(mid) for mid in move_ids if mid and not isinstance(mid, bool)})
        if not ids_limpios:
            return {}

        amls = (
            self.call(
                "account.move.line",
                "search_read",
                [
                    [
                        ["move_id", "in", ids_limpios],
                        ["account_type", "in", ["asset_receivable", "liability_payable"]],
                    ]
                ],
                {
                    "fields": [
                        "id",
                        "move_id",
                        "account_type",
                        "matched_debit_ids",
                        "matched_credit_ids",
                        "currency_id",
                    ]
                },
            )
            or []
        )
        if not amls:
            return {}

        pay_line_by_id: dict[int, dict] = {}
        pr_ids_set: set[int] = set()
        for aml in amls:
            lid = self._m2o_id(aml.get("id"))
            if lid is None:
                continue
            pay_line_by_id[lid] = aml
            for pid in list(aml.get("matched_debit_ids") or []) + list(aml.get("matched_credit_ids") or []):
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                    pr_ids_set.add(pid)

        pr_ids = sorted(pr_ids_set)
        if not pr_ids:
            return {}

        pr_base = ["id", "debit_move_id", "credit_move_id", "amount"]
        pr_fields = self._campos_disponibles(
            "account.partial.reconcile",
            pr_base,
            (
                "debit_amount_currency",
                "credit_amount_currency",
                "debit_currency_id",
                "credit_currency_id",
            ),
            # Fail-safe para Odoo < 14 o cuando fields_get falla/devuelve vacío.
            pr_base,
        )

        partials = (
            self.call(
                "account.partial.reconcile",
                "read",
                [pr_ids],
                {"fields": pr_fields},
            )
            or []
        )
        if not partials:
            return {}

        enlaces: list[tuple[dict, int, int, str]] = []
        counterpart_line_ids_set: set[int] = set()
        for pr in partials:
            debit_line_id = self._m2o_id(pr.get("debit_move_id"))
            credit_line_id = self._m2o_id(pr.get("credit_move_id"))
            if credit_line_id in pay_line_by_id and debit_line_id is not None and debit_line_id not in pay_line_by_id:
                enlaces.append((pr, credit_line_id, debit_line_id, "credit"))
                counterpart_line_ids_set.add(debit_line_id)
            elif (
                debit_line_id in pay_line_by_id and credit_line_id is not None and credit_line_id not in pay_line_by_id
            ):
                enlaces.append((pr, debit_line_id, credit_line_id, "debit"))
                counterpart_line_ids_set.add(credit_line_id)

        counterpart_line_ids = sorted(counterpart_line_ids_set)
        if not counterpart_line_ids:
            return {}

        counterpart_lines = (
            self.call(
                "account.move.line",
                "read",
                [counterpart_line_ids],
                {"fields": ["id", "move_id", "currency_id"]},
            )
            or []
        )
        counterpart_lines_by_id: dict[int, dict] = {}
        counterpart_move_ids_set: set[int] = set()
        for line in counterpart_lines:
            lid = self._m2o_id(line.get("id"))
            if lid is None:
                continue
            counterpart_lines_by_id[lid] = line
            mv_id = self._m2o_id(line.get("move_id"))
            if mv_id is not None:
                counterpart_move_ids_set.add(mv_id)

        counterpart_move_ids = sorted(counterpart_move_ids_set)
        if not counterpart_move_ids:
            return {}

        counterpart_moves = (
            self.call(
                "account.move",
                "read",
                [counterpart_move_ids],
                {"fields": ["id", "move_type", "name", "currency_id"]},
            )
            or []
        )
        counterpart_moves_by_id: dict[int, dict] = {
            mid: mv for mv in counterpart_moves if (mid := self._m2o_id(mv.get("id"))) is not None
        }

        resultado: dict[int, list[dict]] = {}
        vistos: set[tuple[int, int]] = set()
        tipos_factura = {"out_invoice", "in_invoice", "out_refund", "in_refund"}

        for pr, pay_line_id, cp_line_id, lado_pago in enlaces:
            pr_id = self._m2o_id(pr.get("id"))
            pay_aml = pay_line_by_id.get(pay_line_id)
            cp_aml = counterpart_lines_by_id.get(cp_line_id)
            if pr_id is None or pay_aml is None or cp_aml is None:
                continue
            pay_move_id = self._m2o_id(pay_aml.get("move_id"))
            cp_move_id = self._m2o_id(cp_aml.get("move_id"))
            if pay_move_id is None or cp_move_id is None:
                continue
            cp_move = counterpart_moves_by_id.get(cp_move_id)
            if cp_move is None:
                continue
            move_type = str(cp_move.get("move_type") or "")
            if move_type not in tipos_factura:
                continue
            clave = (pay_move_id, pr_id)
            if clave in vistos:
                continue
            vistos.add(clave)

            monto_base = self._to_decimal(pr.get("amount"))
            if lado_pago == "credit":
                raw_pago = pr.get("credit_amount_currency")
                raw_doc = pr.get("debit_amount_currency")
                moneda_pago = self._m2o_name(pr.get("credit_currency_id") or pay_aml.get("currency_id"))
                moneda_doc = self._m2o_name(
                    pr.get("debit_currency_id") or cp_aml.get("currency_id") or cp_move.get("currency_id")
                )
            else:
                raw_pago = pr.get("debit_amount_currency")
                raw_doc = pr.get("credit_amount_currency")
                moneda_pago = self._m2o_name(pr.get("debit_currency_id") or pay_aml.get("currency_id"))
                moneda_doc = self._m2o_name(
                    pr.get("credit_currency_id") or cp_aml.get("currency_id") or cp_move.get("currency_id")
                )

            monto_pago = self._to_decimal(raw_pago) if raw_pago not in (None, False, "", 0, 0.0) else monto_base
            monto_doc = self._to_decimal(raw_doc) if raw_doc not in (None, False, "", 0, 0.0) else monto_base

            resultado.setdefault(pay_move_id, []).append(
                {
                    "partial_reconcile_id": pr_id,
                    "move_id_externo": str(cp_move_id),
                    "move_name": str(cp_move.get("name") or ""),
                    "move_type": move_type,
                    "monto_base": monto_base,
                    "monto_pago": monto_pago,
                    "monto_documento": monto_doc,
                    "moneda_pago": moneda_pago,
                    "moneda_documento": moneda_doc,
                }
            )

        for recs in resultado.values():
            recs.sort(key=lambda item: item["partial_reconcile_id"])
        return resultado

    # ── Inventario ────────────────────────────────────────────────────────────

    def get_stock_actual(self, limite: int = 500) -> list[dict]:
        """
        Stock actual por producto y ubicación (stock.quant).
        Solo ubicaciones internas.
        """
        return self.call(
            "stock.quant",
            "search_read",
            [[["location_id.usage", "=", "internal"]]],
            {
                "fields": [
                    "id",
                    "product_id",
                    "location_id",
                    "quantity",
                    "reserved_quantity",
                    "lot_id",
                ],
                "limit": limite,
            },
        )

    def get_movimientos_stock(self, desde: str | None = None, limite: int = 300) -> list[dict]:
        """Movimientos de stock realizados (stock.move en estado done)."""
        domain: list = [["state", "=", "done"]]
        if desde:
            domain.append(["date", ">=", desde])
        return self.call(
            "stock.move",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "product_id",
                    "product_uom_qty",
                    "quantity_done",
                    "location_id",
                    "location_dest_id",
                    "picking_id",
                    "date",
                    "origin",
                    "state",
                ],
                "limit": limite,
                "order": "date desc",
            },
        )

    # ── Información del sistema ───────────────────────────────────────────────

    def get_diarios(self, tipos: list[str] | None = None) -> list[dict]:
        """Diarios contables (account.journal)."""
        domain: list = []
        if tipos:
            domain.append(["type", "in", tipos])
        return self.call(
            "account.journal",
            "search_read",
            [domain],
            {"fields": ["id", "name", "type", "currency_id"], "limit": 100},
        )

    def get_monedas(self) -> list[dict]:
        """Monedas activas."""
        return self.call(
            "res.currency",
            "search_read",
            [[["active", "=", True]]],
            {"fields": ["id", "name", "symbol", "rate"], "limit": 50},
        )

    def get_paises(self) -> list[dict]:
        """Lista de países."""
        return self.call(
            "res.country",
            "search_read",
            [[]],
            {"fields": ["id", "name", "code"], "limit": 300},
        )

    # ── Escritura ─────────────────────────────────────────────────────────────

    def crear_socio(self, vals: dict) -> int:
        """Crea un socio en Odoo y retorna su ID."""
        # Limpiar Nones (XML-RPC no los acepta en ciertos campos)
        clean = {k: v for k, v in vals.items() if v is not None}
        result = self.call("res.partner", "create", [clean])
        return result[0] if isinstance(result, list) else result

    def actualizar_socio(self, partner_id: int, vals: dict) -> bool:
        """Actualiza un socio existente."""
        clean = {k: v for k, v in vals.items() if v is not None}
        return self.call("res.partner", "write", [[partner_id], clean])

    def crear_producto(self, vals: dict) -> int:
        """Crea una plantilla de producto en Odoo."""
        clean = {k: v for k, v in vals.items() if v is not None}
        result = self.call("product.template", "create", [clean])
        return result[0] if isinstance(result, list) else result

    def actualizar_producto(self, tmpl_id: int, vals: dict) -> bool:
        """Actualiza una plantilla de producto."""
        clean = {k: v for k, v in vals.items() if v is not None}
        return self.call("product.template", "write", [[tmpl_id], clean])

    def crear_pedido_venta(self, vals: dict) -> int:
        """Crea una ``sale.order`` (queda en borrador/cotización) y retorna su ID."""
        clean = {k: v for k, v in vals.items() if v is not None}
        result = self.call("sale.order", "create", [clean])
        return result[0] if isinstance(result, list) else result

    def crear_pago(self, vals: dict) -> int:
        """Crea un ``account.payment`` en borrador (sin publicar) y retorna su ID."""
        clean = {k: v for k, v in vals.items() if v is not None}
        result = self.call("account.payment", "create", [clean])
        return result[0] if isinstance(result, list) else result
