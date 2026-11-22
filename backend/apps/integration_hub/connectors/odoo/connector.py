"""
OdooConnector — Conector Odoo para el Integration Hub de Omni ERP.

Soporta Odoo 8 a 18+ vía XML-RPC.
Implementa la interfaz BaseConnector para:
  - Contactos (clientes + proveedores)
  - Productos
  - Pedidos de venta
  - Pedidos de compra
  - Facturas de venta
  - Pagos (inbound y outbound)
  - Inventario (stock actual)

Configuración requerida en ConectorInstancia.configuracion:
    {
        "host": "https://miodoo.odoo.com",
        "db": "mi_base_de_datos",
        "user": "admin@empresa.com",
        "api_key": "clave_api_o_password"
    }

Configuración opcional:
    {
        ...
        "timeout": 30,          # segundos (default: 30)
        "limite_default": 200   # registros por llamada (default: 200)
    }
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    ConnectorDataError,
    TestConnectionResult,
)
from apps.integration_hub.connectors.odoo.client import (
    OdooAuthError,
    OdooCallError,
    OdooXMLRPCClient,
    normalize_odoo_host,
    sanitizar_error_odoo,
)

if TYPE_CHECKING:
    from apps.integration_hub.models import ConectorInstancia

logger = logging.getLogger(__name__)


class OdooConnector(BaseConnector):
    """
    Conector para Odoo (todas las versiones vía XML-RPC).

    Normaliza los datos de Odoo a formatos Omni para facilitar la
    sincronización bidireccional.
    """

    PROVIDER_CODE = "odoo"
    PROVIDER_NAME = "Odoo"
    SUPPORTED_ENTITIES = [
        "contactos",
        "productos",
        "pedidos_venta",
        "pedidos_compra",
        "facturas_venta",
        "facturas_compra",
        "pagos",
        "gestiones_cobranza",
        "inventario",
    ]

    def __init__(self, instancia: "ConectorInstancia"):
        super().__init__(instancia)
        self._client: OdooXMLRPCClient | None = None
        self._write_client: OdooXMLRPCClient | None = None
        self._connect_write_client: OdooXMLRPCClient | None = None
        self._model_fields_cache: dict[str, set[str]] = {}

    def _sanitizar_error_externo(self, exc: BaseException | str) -> str:
        """Enmascara credenciales y trazas sensibles en errores de Odoo (R-CODE-8)."""
        cfg = getattr(self, "_config", None) or {}
        secretos = [
            str(cfg.get(k) or "") for k in ("api_key", "write_api_key", "password", "token", "secret") if cfg.get(k)
        ]
        return sanitizar_error_odoo(exc, secrets=secretos)

    def _get_client(self) -> OdooXMLRPCClient:
        """Retorna o crea el cliente XML-RPC. Reconecta si es necesario."""
        if self._client is not None:
            try:
                if self._client.ping():
                    return self._client
                logger.warning("OdooConnector: ping fallido — reconectando")
            except Exception:
                pass
            self._client = None

        cfg = self._config
        host = cfg.get("host", "")
        db = cfg.get("db", "")
        user = cfg.get("user", "")
        api_key = cfg.get("api_key", "")
        timeout = int(cfg.get("timeout", 30))

        if not all([host, user, api_key]):
            raise ConnectorConnectionError(
                "La configuración del conector Odoo está incompleta. "
                "Se requieren: host, user, api_key. "
                "db es opcional para Odoo SaaS (que auto-detecta la BD)."
            )

        try:
            self._client = OdooXMLRPCClient(host, db, user, api_key, timeout)
        except OdooAuthError as exc:
            raise ConnectorConnectionError(self._sanitizar_error_externo(exc)) from exc

        return self._client

    def _get_write_client(self) -> OdooXMLRPCClient:
        """Retorna cliente XML-RPC para escrituras outbound (fail-closed, R-CODE-8).

        - Exige ``push_habilitado=True`` en la configuración del conector.
        - Si existen ``write_user`` o ``write_api_key``, exige simetría estricta;
          si falta alguno, falla cerrado sin caer a las credenciales principales.
        - Si ninguno fue configurado y ``push_habilitado=True``, usa ``_get_client()``.
        """
        cfg = getattr(self, "_config", None) or {}
        if not cfg.get("push_habilitado", False):
            raise ConnectorConnectionError("Push outbound deshabilitado en este conector (push_habilitado=False).")

        write_user = str(cfg.get("write_user") or "").strip()
        write_key = str(cfg.get("write_api_key") or "").strip()

        if bool(write_user) != bool(write_key):
            raise ConnectorConnectionError(
                "Configuración de escritura incompleta: debe definir tanto 'write_user' como 'write_api_key'."
            )

        if write_user and write_key:
            write_client = getattr(self, "_write_client", None)
            if write_client is not None:
                try:
                    if write_client.ping():
                        return write_client
                    logger.warning("OdooConnector: ping cliente de escritura fallido — reconectando")
                except Exception:
                    pass
                self._write_client = None

            host = cfg.get("host", "")
            db = cfg.get("db", "")
            timeout = int(cfg.get("timeout", 30))
            if not host:
                raise ConnectorConnectionError("La configuración del conector Odoo está incompleta: falta 'host'.")
            try:
                self._write_client = OdooXMLRPCClient(host, db, write_user, write_key, timeout)
            except OdooAuthError as exc:
                raise ConnectorConnectionError(self._sanitizar_error_externo(exc)) from None
            return self._write_client

        return self._get_client()

    def _get_connect_lead_write_client(self) -> OdooXMLRPCClient:
        """Cliente XML-RPC fail-closed exclusivo para push de leads Connect hacia ``crm.lead``.

        - Exige opt-in booleano estricto ``empujar_connect_leads=True``.
        - Exige credenciales de escritura dedicadas ``write_user`` y ``write_api_key``
          (NUNCA cae a las credenciales de lectura ``user``/``api_key``).
        """
        cfg = getattr(self, "_config", None) or {}
        if cfg.get("empujar_connect_leads") is not True:
            raise ConnectorConnectionError(
                "Push de leads Connect deshabilitado en este conector (empujar_connect_leads debe ser True)."
            )

        write_user = str(cfg.get("write_user") or "").strip()
        write_key = str(cfg.get("write_api_key") or "").strip()
        if not write_user or not write_key:
            raise ConnectorConnectionError(
                "Push de leads Connect requiere credenciales de escritura dedicadas ('write_user' y 'write_api_key')."
            )

        connect_client = getattr(self, "_connect_write_client", None)
        if connect_client is not None:
            try:
                if connect_client.ping():
                    return connect_client
            except Exception:
                pass
            self._connect_write_client = None

        host = str(cfg.get("host") or "").strip()
        db = str(cfg.get("db") or "").strip()
        timeout = int(cfg.get("timeout", 30))
        if not host:
            raise ConnectorConnectionError("La configuración del conector Odoo está incompleta: falta 'host'.")
        try:
            self._connect_write_client = OdooXMLRPCClient(
                host,
                db,
                write_user,
                write_key,
                timeout,
                write_user=write_user,
                write_api_key=write_key,
            )
        except OdooAuthError as exc:
            raise ConnectorConnectionError(self._sanitizar_error_externo(exc)) from None
        return self._connect_write_client

    def _get_model_fields(self, client: Any, model_name: str) -> set[str]:
        """Detecta y cachea los campos disponibles de un modelo Odoo (compatible v8–v18+)."""
        cache = getattr(self, "_model_fields_cache", None)
        if cache is None:
            cache = {}
            self._model_fields_cache = cache
        cache_key = f"{id(client)}:{model_name}"
        if cache_key in cache:
            return cache[cache_key]

        campos: set[str] | None = None
        if hasattr(client, "_get_model_fields"):
            cand = client._get_model_fields(model_name)
            if isinstance(cand, (set, list, tuple, frozenset)):
                campos = {str(k) for k in cand}
        if campos is None:
            try:
                resp = client.call(model_name, "fields_get", [[]], {"attributes": ["string"]})
                campos = {str(k) for k in resp.keys()} if isinstance(resp, dict) else set()
            except Exception:
                campos = set()
        cache[cache_key] = campos
        return campos

    # ── Conexión ──────────────────────────────────────────────────────────────

    def test_connection(self) -> TestConnectionResult:
        """
        Prueba la conexión con Odoo. Retorna TestConnectionResult.
        Detecta la versión del servidor automáticamente.
        """
        try:
            client = self._get_client()
            version_info = client.get_version()
            version_str = version_info.get("server_version", "desconocida")

            # Verificar permisos básicos de lectura
            client.call("res.lang", "search_count", [[]])

            return TestConnectionResult(
                success=True,
                message=f"Conexión exitosa con Odoo {version_str}",
                version=version_str,
                details={
                    "server_version": version_str,
                    "server_version_info": version_info.get("server_version_info", []),
                    "protocol_version": version_info.get("protocol_version", ""),
                    "uid": client.uid,
                },
            )
        except ConnectorConnectionError as exc:
            return TestConnectionResult(
                success=False,
                message=str(exc),
            )
        except Exception as exc:
            return TestConnectionResult(
                success=False,
                message=f"Error inesperado: {type(exc).__name__}",
                details={"error": str(exc)},
            )

    def get_version_info(self) -> dict:
        client = self._get_client()
        return client.get_version()

    # ── Contactos ─────────────────────────────────────────────────────────────

    def pull_contactos(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        """
        Trae todos los socios activos de Odoo (clientes Y proveedores).
        Retorna lista de dicts normalizados al formato Omni.
        """
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d %H:%M:%S") if desde else None

        try:
            socios = client.get_socios(desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo contactos de Odoo: {exc}") from exc

        return [self.normalizar_contacto(s) for s in socios]

    def normalizar_contacto(self, raw: dict) -> dict:
        """
        Transforma un res.partner de Odoo al formato de Contacto de Omni.

        Campos Omni esperados:
            id_externo, nombre, email, telefono, movil,
            es_cliente, es_proveedor, es_empresa,
            identificador_fiscal, direccion, ciudad,
            pais_codigo, notas, fecha_modificacion_externo
        """
        country = raw.get("country_id") or []
        state = raw.get("state_id") or []
        parent = raw.get("parent_id") or []

        return {
            "id_externo": str(raw["id"]),
            "nombre": raw.get("name") or "",
            "email": raw.get("email") or "",
            "telefono": raw.get("phone") or "",
            "movil": raw.get("mobile") or "",
            "es_cliente": int(raw.get("customer_rank") or 0) > 0,
            "es_proveedor": int(raw.get("supplier_rank") or 0) > 0,
            "es_empresa": raw.get("company_type") == "company",
            "identificador_fiscal": raw.get("vat") or "",
            "direccion": raw.get("street") or "",
            "ciudad": raw.get("city") or "",
            "pais_codigo": (
                country[1] if isinstance(country, list) and len(country) > 1 else str(country) if country else ""
            ),
            "pais_nombre": (country[1] if isinstance(country, list) and len(country) > 1 else ""),
            "estado_provincia": (state[1] if isinstance(state, list) and len(state) > 1 else ""),
            "empresa_padre_id": (str(parent[0]) if isinstance(parent, list) and parent else ""),
            "website": raw.get("website") or "",
            "notas": raw.get("comment") or "",
            "activo": raw.get("active", True),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "fecha_creacion_externo": (raw.get("create_date") or "")[:19],
            # Checksum para detección de cambios
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Productos ─────────────────────────────────────────────────────────────

    def pull_productos(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        """Trae productos activos de Odoo normalizados."""
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d %H:%M:%S") if desde else None

        try:
            productos = client.get_productos(desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo productos de Odoo: {exc}") from exc

        return [self.normalizar_producto(p) for p in productos]

    def normalizar_producto(self, raw: dict) -> dict:
        """
        Transforma un product.template de Odoo al formato Omni.

        Mapeo:
            Odoo list_price → precio_venta
            Odoo standard_price → costo
            Odoo default_code → codigo_interno / referencia
            Odoo categ_id → categoria_nombre
            Odoo uom_id → unidad_medida
            Odoo type → tipo (consu→consumible, service→servicio, product→almacenable)
        """
        categ = raw.get("categ_id") or []
        uom = raw.get("uom_id") or []
        uom_po = raw.get("uom_po_id") or []

        tipo_map = {
            "consu": "consumible",
            "service": "servicio",
            "product": "almacenable",
        }

        return {
            "id_externo": str(raw["id"]),
            "nombre": raw.get("name") or "",
            "codigo_interno": raw.get("default_code") or "",
            "descripcion_venta": raw.get("description_sale") or "",
            "precio_venta": self._safe_decimal(raw.get("list_price")),
            "costo": self._safe_decimal(raw.get("standard_price")),
            "categoria_id_externo": str(categ[0]) if isinstance(categ, list) and categ else "",
            "categoria_nombre": (categ[1] if isinstance(categ, list) and len(categ) > 1 else ""),
            "unidad_medida": (uom[1] if isinstance(uom, list) and len(uom) > 1 else ""),
            "unidad_compra": (uom_po[1] if isinstance(uom_po, list) and len(uom_po) > 1 else ""),
            "tipo": tipo_map.get(raw.get("type") or "", "almacenable"),
            "disponible_venta": raw.get("sale_ok", True),
            "disponible_compra": raw.get("purchase_ok", True),
            "codigo_barras": raw.get("barcode") or "",
            "peso": self._safe_float(raw.get("weight")),
            "volumen": self._safe_float(raw.get("volume")),
            "activo": raw.get("active", True),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "fecha_creacion_externo": (raw.get("create_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Pedidos de Venta ──────────────────────────────────────────────────────

    def pull_pedidos_venta(self, desde: datetime | None = None, limite: int = 200) -> list[dict]:
        """Trae pedidos de venta confirmados de Odoo."""
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d %H:%M:%S") if desde else None

        try:
            pedidos = client.get_pedidos_venta(desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo pedidos de venta de Odoo: {exc}") from exc

        normalizados = []
        for p in pedidos:
            norm = self._normalizar_pedido_venta(p)
            # Traer líneas solo si el pedido está en scope
            try:
                norm["lineas"] = client.get_lineas_pedido_venta(p["id"])
            except Exception:
                norm["lineas"] = []
            normalizados.append(norm)

        return normalizados

    def _normalizar_pedido_venta(self, raw: dict) -> dict:
        partner = raw.get("partner_id") or []
        user = raw.get("user_id") or []
        currency = raw.get("currency_id") or []
        pricelist = raw.get("pricelist_id") or []
        payment_term = raw.get("payment_term_id") or []

        estado_map = {
            "draft": "borrador",
            "sent": "enviado",
            "sale": "confirmado",
            "done": "cerrado",
            "cancel": "cancelado",
        }
        factura_map = {
            "nothing": "sin_facturar",
            "to invoice": "por_facturar",
            "no": "sin_facturar",
            "invoiced": "facturado",
        }

        return {
            "id_externo": str(raw["id"]),
            "numero": raw.get("name") or "",
            "cliente_id_externo": str(partner[0]) if isinstance(partner, list) and partner else "",
            "cliente_nombre": (partner[1] if isinstance(partner, list) and len(partner) > 1 else ""),
            "vendedor_nombre": (user[1] if isinstance(user, list) and len(user) > 1 else ""),
            "fecha_pedido": (raw.get("date_order") or "")[:10],
            "estado": estado_map.get(raw.get("state") or "", raw.get("state") or ""),
            "estado_factura": factura_map.get(raw.get("invoice_status") or "", raw.get("invoice_status") or ""),
            "subtotal": self._safe_decimal(raw.get("amount_untaxed")),
            "impuestos": self._safe_decimal(raw.get("amount_tax")),
            "total": self._safe_decimal(raw.get("amount_total")),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1 else "USD"),
            "lista_precios": (pricelist[1] if isinstance(pricelist, list) and len(pricelist) > 1 else ""),
            "termino_pago": (payment_term[1] if isinstance(payment_term, list) and len(payment_term) > 1 else ""),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Pedidos de Compra ─────────────────────────────────────────────────────

    def pull_pedidos_compra(self, desde: datetime | None = None, limite: int = 200) -> list[dict]:
        """Trae órdenes de compra confirmadas de Odoo."""
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d %H:%M:%S") if desde else None

        try:
            pedidos = client.get_pedidos_compra(desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo pedidos de compra de Odoo: {exc}") from exc

        normalizados = []
        for p in pedidos:
            norm = self._normalizar_pedido_compra(p)
            try:
                norm["lineas"] = client.get_lineas_pedido_compra(p["id"])
            except Exception:
                norm["lineas"] = []
            normalizados.append(norm)

        return normalizados

    def _normalizar_pedido_compra(self, raw: dict) -> dict:
        partner = raw.get("partner_id") or []
        currency = raw.get("currency_id") or []

        return {
            "id_externo": str(raw["id"]),
            "numero": raw.get("name") or "",
            "proveedor_id_externo": str(partner[0]) if isinstance(partner, list) and partner else "",
            "proveedor_nombre": (partner[1] if isinstance(partner, list) and len(partner) > 1 else ""),
            "fecha_pedido": (raw.get("date_order") or "")[:10],
            "fecha_aprobacion": (raw.get("date_approve") or "")[:10],
            "estado": raw.get("state") or "",
            "estado_factura": raw.get("invoice_status") or "",
            "subtotal": self._safe_decimal(raw.get("amount_untaxed")),
            "impuestos": self._safe_decimal(raw.get("amount_tax")),
            "total": self._safe_decimal(raw.get("amount_total")),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1 else "USD"),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Facturas de Venta y Compra ────────────────────────────────────────────

    def _pull_facturas_por_tipo(
        self,
        *,
        tipo_move: str,
        etiqueta_error: str,
        normalizer,
        desde: datetime | None = None,
        limite: int = 200,
    ) -> list[dict]:
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d %H:%M:%S") if desde else None

        try:
            facturas = client.get_facturas(tipo=tipo_move, desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo {etiqueta_error} de Odoo: {exc}") from exc

        normalizados = []
        for f in facturas:
            norm = normalizer(f)
            # Traer líneas (account.move.line); si falla, factura sin líneas.
            try:
                norm["lineas"] = client.get_lineas_factura(f["id"])
            except Exception:
                norm["lineas"] = []
            normalizados.append(norm)

        return normalizados

    def pull_facturas_venta(self, desde: datetime | None = None, limite: int = 200) -> list[dict]:
        """Trae facturas de venta publicadas de Odoo."""
        return self._pull_facturas_por_tipo(
            tipo_move="out_invoice",
            etiqueta_error="facturas",
            normalizer=self._normalizar_factura,
            desde=desde,
            limite=limite,
        )

    def pull_facturas_compra(self, desde: datetime | None = None, limite: int = 200) -> list[dict]:
        """Trae facturas de proveedor (in_invoice) publicadas de Odoo."""
        return self._pull_facturas_por_tipo(
            tipo_move="in_invoice",
            etiqueta_error="facturas de compra",
            normalizer=self._normalizar_factura_compra,
            desde=desde,
            limite=limite,
        )

    def _normalizar_factura_base(self, raw: dict, *, id_key: str, nombre_key: str) -> dict:
        partner = raw.get("partner_id") or []
        currency = raw.get("currency_id") or []

        pago_estado_map = {
            "not_paid": "pendiente",
            "in_payment": "en_proceso",
            "paid": "pagado",
            "partial": "parcial",
            "reversed": "revertido",
        }

        return {
            "id_externo": str(raw["id"]),
            "numero": raw.get("name") or "",
            "referencia": raw.get("ref") or "",
            "origen_pedido": raw.get("invoice_origin") or "",
            id_key: str(partner[0]) if isinstance(partner, list) and partner else "",
            nombre_key: (partner[1] if isinstance(partner, list) and len(partner) > 1 else ""),
            "fecha_factura": (raw.get("invoice_date") or "")[:10],
            "fecha_vencimiento": (raw.get("invoice_date_due") or "")[:10],
            "subtotal": self._safe_decimal(raw.get("amount_untaxed")),
            "impuestos": self._safe_decimal(raw.get("amount_tax")),
            "total": self._safe_decimal(raw.get("amount_total")),
            "saldo_pendiente": self._safe_decimal(raw.get("amount_residual")),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1 else "USD"),
            "estado_pago": pago_estado_map.get(raw.get("payment_state") or "", raw.get("payment_state") or ""),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    def _normalizar_factura(self, raw: dict) -> dict:
        return self._normalizar_factura_base(
            raw,
            id_key="cliente_id_externo",
            nombre_key="cliente_nombre",
        )

    def _normalizar_factura_compra(self, raw: dict) -> dict:
        return self._normalizar_factura_base(
            raw,
            id_key="proveedor_id_externo",
            nombre_key="proveedor_nombre",
        )

    # ── Pagos ─────────────────────────────────────────────────────────────────

    def pull_pagos(self, desde: datetime | None = None, limite: int = 300) -> list[dict]:
        """Trae pagos (inbound + outbound) de Odoo con reconciliaciones parciales en lote."""
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d") if desde else None

        try:
            pagos = client.get_pagos(desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo pagos de Odoo: {exc}") from exc

        move_ids: list[int] = []
        for p in pagos:
            mv = p.get("move_id")
            mid = mv[0] if isinstance(mv, (list, tuple)) and mv else mv
            if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0:
                move_ids.append(mid)

        recons_por_move: dict[int, list[dict]] = {}
        if move_ids:
            try:
                recons = client.get_reconciliaciones_pagos(move_ids)
                if isinstance(recons, dict):
                    recons_por_move = recons
            except (AttributeError, OdooCallError):
                recons_por_move = {}

        resultado: list[dict] = []
        for p in pagos:
            mv = p.get("move_id")
            mid = mv[0] if isinstance(mv, (list, tuple)) and mv else mv
            recons_pago = recons_por_move.get(mid) if isinstance(mid, int) and not isinstance(mid, bool) else None
            resultado.append(self._normalizar_pago(p, reconciliaciones=recons_pago))
        return resultado

    def _normalizar_pago(self, raw: dict, reconciliaciones: list[dict] | None = None) -> dict:
        partner = raw.get("partner_id") or []
        journal = raw.get("journal_id") or []
        currency = raw.get("currency_id") or []

        facturas_ext: list[str] = []
        seen_facturas: set[str] = set()
        for inv_id in list(raw.get("reconciled_invoice_ids") or []) + list(raw.get("reconciled_bill_ids") or []):
            sid = str(inv_id)
            if sid and sid not in seen_facturas:
                seen_facturas.add(sid)
                facturas_ext.append(sid)

        recons_norm: list[dict] = []
        for rec in reconciliaciones or []:
            move_id_ext = str(rec.get("move_id_externo") or "")
            if move_id_ext and move_id_ext not in seen_facturas:
                seen_facturas.add(move_id_ext)
                facturas_ext.append(move_id_ext)
            recons_norm.append(
                {
                    "partial_reconcile_id": str(rec.get("partial_reconcile_id") or ""),
                    "move_id_externo": move_id_ext,
                    "move_type": str(rec.get("move_type") or ""),
                    "monto_base": self._safe_decimal(rec.get("monto_base")),
                    "monto_pago": self._safe_decimal(rec.get("monto_pago")),
                    "monto_documento": self._safe_decimal(rec.get("monto_documento")),
                    "moneda_pago": str(rec.get("moneda_pago") or ""),
                    "moneda_documento": str(rec.get("moneda_documento") or ""),
                }
            )

        checksum_payload = dict(raw)
        if recons_norm:
            checksum_payload["_reconciliaciones"] = recons_norm

        return {
            "id_externo": str(raw["id"]),
            "numero": raw.get("name") or "",
            "tipo": raw.get("payment_type") or "",  # inbound | outbound
            "tipo_socio": raw.get("partner_type") or "",  # customer | supplier
            "socio_id_externo": str(partner[0]) if isinstance(partner, list) and partner else "",
            "socio_nombre": (partner[1] if isinstance(partner, list) and len(partner) > 1 else ""),
            "monto": self._safe_decimal(raw.get("amount")),
            "fecha": (raw.get("date") or "")[:10],
            "estado": raw.get("state") or "",
            "diario": (journal[1] if isinstance(journal, list) and len(journal) > 1 else ""),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1 else "USD"),
            # Facturas (account.move) reconciliadas por este pago → reconciliación.
            "facturas_externas": facturas_ext,
            "reconciliaciones": recons_norm,
            "referencia": raw.get("memo") or raw.get("payment_reference") or raw.get("ref") or "",
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(checksum_payload),
            "_fuente": "odoo",
        }

    # ── Inventario ────────────────────────────────────────────────────────────

    def pull_inventario(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        """Trae stock actual por producto y ubicación de Odoo."""
        client = self._get_client()

        try:
            quants = client.get_stock_actual(limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo inventario de Odoo: {exc}") from exc

        return [self._normalizar_stock_quant(q) for q in quants]

    def _normalizar_stock_quant(self, raw: dict) -> dict:
        product = raw.get("product_id") or []
        location = raw.get("location_id") or []
        lot = raw.get("lot_id") or []

        return {
            "id_externo": str(raw["id"]),
            "producto_id_externo": str(product[0]) if isinstance(product, list) and product else "",
            "producto_nombre": (product[1] if isinstance(product, list) and len(product) > 1 else ""),
            "ubicacion_id_externo": str(location[0]) if isinstance(location, list) and location else "",
            "ubicacion_nombre": (location[1] if isinstance(location, list) and len(location) > 1 else ""),
            "cantidad": self._safe_float(raw.get("quantity")),
            "cantidad_reservada": self._safe_float(raw.get("reserved_quantity")),
            "cantidad_disponible": max(
                0.0,
                self._safe_float(raw.get("quantity")) - self._safe_float(raw.get("reserved_quantity")),
            ),
            "lote": (lot[1] if isinstance(lot, list) and len(lot) > 1 else ""),
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Push (escritura hacia Odoo) ───────────────────────────────────────────

    def push_contacto(self, datos: dict) -> str:
        """
        Crea o actualiza un contacto en Odoo.
        Si datos tiene 'id_externo', actualiza; si no, crea.
        Retorna el ID externo del socio creado/actualizado.
        """
        client = (
            self._get_write_client()
            if (getattr(self, "_config", None) or {}).get("push_habilitado")
            else self._get_client()
        )
        id_externo = datos.get("id_externo")

        # Mapear campos Omni → Odoo
        vals = {}
        if datos.get("nombre"):
            vals["name"] = datos["nombre"]
        if datos.get("email"):
            vals["email"] = datos["email"]
        if datos.get("telefono"):
            vals["phone"] = datos["telefono"]
        if datos.get("movil"):
            vals["mobile"] = datos["movil"]
        if datos.get("identificador_fiscal"):
            vals["vat"] = datos["identificador_fiscal"]
        if datos.get("direccion"):
            vals["street"] = datos["direccion"]
        if datos.get("ciudad"):
            vals["city"] = datos["ciudad"]
        if datos.get("notas"):
            vals["comment"] = datos["notas"]
        if datos.get("es_cliente"):
            vals["customer_rank"] = 1
        gps = {}
        if datos.get("latitud") is not None and datos.get("longitud") is not None:
            # ``partner_latitude/longitude`` los aporta base_geolocalize; si Odoo no lo tiene se reintenta sin GPS.
            gps = {
                "partner_latitude": float(datos["latitud"]),
                "partner_longitude": float(datos["longitud"]),
            }

        def _guardar(v: dict) -> str:
            if id_externo:
                client.actualizar_socio(int(id_externo), v)
                return id_externo
            return str(client.crear_socio(v))

        if not gps:
            return _guardar(vals)
        try:
            return _guardar({**vals, **gps})
        except OdooCallError as exc:
            if "partner_latitude" not in str(exc) and "partner_longitude" not in str(exc):
                raise
            logger.warning("Odoo sin campos de geolocalización: se guarda el contacto sin GPS")
            return _guardar(vals)

    def push_pedido_venta(self, datos: dict) -> str:
        """
        Crea un pedido de venta en Odoo (``sale.order`` en borrador, queda por confirmar allí).

        ``datos`` (ids ya resueltos al espacio de Odoo):
        ``partner_id`` (int), ``lineas`` [{``product_id`` (product.product), ``cantidad``, ``precio``}],
        opcionales ``referencia`` (client_order_ref), ``nota``, ``vendedor_id`` (res.users),
        ``pricelist_id``, ``fecha_entrega`` (commitment_date ISO).
        """
        if not datos.get("partner_id") or not datos.get("lineas"):
            raise ConnectorDataError("push_pedido_venta requiere partner_id y al menos una línea")
        vals = {
            "partner_id": int(datos["partner_id"]),
            "client_order_ref": datos.get("referencia"),
            "note": datos.get("nota"),
            "user_id": int(datos["vendedor_id"]) if datos.get("vendedor_id") else None,
            "pricelist_id": int(datos["pricelist_id"]) if datos.get("pricelist_id") else None,
            "commitment_date": datos.get("fecha_entrega"),
            "order_line": [
                (
                    0,
                    0,
                    {
                        "product_id": int(ln["product_id"]),
                        "product_uom_qty": float(ln["cantidad"]),
                        "price_unit": float(ln["precio"]),
                    },
                )
                for ln in datos["lineas"]
            ],
        }
        return str(self._get_client().crear_pedido_venta(vals))

    def push_pago(self, datos: dict) -> str:
        """
        Crea un pago en Odoo (``account.payment`` en borrador, sin publicar: se confirma en Odoo).

        ``datos``: ``partner_id``, ``monto`` (>0), ``journal_id``, ``tipo`` (``cliente`` | ``proveedor``);
        opcionales ``moneda_id``, ``fecha`` (ISO), ``referencia`` (memo).
        """
        for campo in ("partner_id", "monto", "journal_id"):
            if not datos.get(campo):
                raise ConnectorDataError(f"push_pago requiere {campo}")
        if float(datos["monto"]) <= 0:
            raise ConnectorDataError("push_pago: el monto debe ser mayor que cero")
        es_cliente = datos.get("tipo", "cliente") == "cliente"
        vals = {
            "partner_id": int(datos["partner_id"]),
            "amount": float(datos["monto"]),
            "payment_type": "inbound" if es_cliente else "outbound",
            "partner_type": "customer" if es_cliente else "supplier",
            "journal_id": int(datos["journal_id"]),
            "currency_id": int(datos["moneda_id"]) if datos.get("moneda_id") else None,
            "date": datos.get("fecha"),
            "memo": datos.get("referencia"),  # Odoo 18: ``memo`` (antes ``ref``)
        }
        return str(self._get_client().crear_pago(vals))

    def _detectar_campo_ref_pago(self, client: Any) -> str:
        """Detecta el campo de memo/referencia de ``account.payment`` (v18: memo; <18: payment_reference/ref)."""
        campos = self._get_model_fields(client, "account.payment")
        for candidato in ("memo", "payment_reference", "ref"):
            if candidato in campos:
                return candidato
        return "memo"

    def _conciliar_pago_con_facturas(self, client: Any, pago_id: int, facturas_odoo_ids: list[int]) -> None:
        """Concilia líneas abiertas receivable/payable del asiento del pago contra las facturas indicadas."""
        aml_fields = self._get_model_fields(client, "account.move.line")
        if "account_internal_type" in aml_fields and "account_type" not in aml_fields:
            tipo_cond: list[Any] = ["account_internal_type", "in", ["receivable", "payable"]]
        else:
            tipo_cond = ["account_type", "in", ["asset_receivable", "liability_payable"]]

        pay_rows = client.call("account.payment", "read", [[pago_id]], {"fields": ["id", "move_id"]}) or []
        pay_move_id = None
        if pay_rows and isinstance(pay_rows[0], dict):
            pay_move_id = OdooXMLRPCClient._m2o_id(pay_rows[0].get("move_id"))

        if pay_move_id is not None:
            pay_domain: list[Any] = [["move_id", "=", pay_move_id], tipo_cond, ["reconciled", "=", False]]
        else:
            pay_domain = [["payment_id", "=", pago_id], tipo_cond, ["reconciled", "=", False]]

        pay_line_ids = client.call("account.move.line", "search", [pay_domain]) or []
        inv_line_ids = (
            client.call(
                "account.move.line",
                "search",
                [
                    [
                        ["move_id", "in", facturas_odoo_ids],
                        ["parent_state", "=", "posted"],
                        tipo_cond,
                        ["reconciled", "=", False],
                    ]
                ],
            )
            or []
        )

        if pay_line_ids and inv_line_ids:
            line_ids = [int(lid) for lid in list(pay_line_ids) + list(inv_line_ids)]
            client.call("account.move.line", "reconcile", [line_ids])
        else:
            logger.warning(
                "push_pago_cobranza: sin líneas abiertas para conciliar pago=%s facturas=%s",
                pago_id,
                facturas_odoo_ids,
            )

    def push_pago_cobranza(self, datos: dict) -> str:
        """Crea un pago de cobranza en Odoo de forma idempotente (borrador o confirmado+conciliado)."""
        partner_raw = datos.get("partner_id")
        if not partner_raw or isinstance(partner_raw, bool):
            raise ConnectorDataError("push_pago_cobranza requiere partner_id válido.")
        try:
            partner_id = int(partner_raw)
        except (TypeError, ValueError) as exc:
            raise ConnectorDataError("push_pago_cobranza: partner_id inválido.") from exc
        if partner_id <= 0:
            raise ConnectorDataError("push_pago_cobranza: partner_id debe ser mayor que cero.")

        monto_raw = datos.get("monto") if datos.get("monto") is not None else datos.get("amount")
        if monto_raw in (None, "", False):
            raise ConnectorDataError("push_pago_cobranza requiere monto.")
        try:
            monto_dec = Decimal(str(monto_raw).strip())
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ConnectorDataError("push_pago_cobranza: monto inválido.") from exc
        if not monto_dec.is_finite() or monto_dec <= Decimal("0"):
            raise ConnectorDataError("push_pago_cobranza: el monto debe ser mayor que cero.")

        cfg = getattr(self, "_config", None) or {}
        journal_raw = datos.get("journal_id") or cfg.get("diario_pagos_default_id")
        if not journal_raw or isinstance(journal_raw, bool):
            raise ConnectorDataError(
                "push_pago_cobranza requiere journal_id o diario_pagos_default_id en el conector."
            )
        try:
            journal_id = int(journal_raw)
        except (TypeError, ValueError) as exc:
            raise ConnectorDataError("push_pago_cobranza: journal_id inválido.") from exc
        if journal_id <= 0:
            raise ConnectorDataError("push_pago_cobranza: journal_id debe ser mayor que cero.")

        modo = str(datos.get("push_modo_pago") or cfg.get("push_modo_pago") or "borrador").strip().lower()
        if modo not in ("borrador", "confirmado"):
            raise ConnectorDataError(f"push_modo_pago inválido: '{modo}'. Use 'borrador' o 'confirmado'.")

        facturas_raw = datos.get("facturas_odoo_ids") or []
        facturas_odoo_ids: list[int] = []
        for fid in facturas_raw:
            if fid in (None, "", False) or isinstance(fid, bool):
                continue
            try:
                fid_int = int(fid)
            except (TypeError, ValueError) as exc:
                raise ConnectorDataError(f"push_pago_cobranza: factura_odoo_id inválido ({fid!r}).") from exc
            if fid_int > 0 and fid_int not in facturas_odoo_ids:
                facturas_odoo_ids.append(fid_int)

        tipo = str(datos.get("tipo") or "cliente").strip().lower()
        es_cliente = tipo in ("cliente", "inbound", "customer")
        fecha = str(datos.get("fecha") or "")[:10]

        raw_key = str(datos.get("idempotency_key") or datos.get("id_omni") or "").strip()
        if not raw_key:
            seed = f"{partner_id}:{monto_dec}:{fecha}:{tipo}:{','.join(map(str, sorted(facturas_odoo_ids)))}"
            raw_key = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        tag = f"[OMNI:{raw_key}]"
        referencia_txt = str(datos.get("referencia") or datos.get("memo") or "").strip()
        memo_final = f"{tag} {referencia_txt}".strip() if tag not in referencia_txt else referencia_txt

        client = self._get_write_client()
        try:
            campo_ref = self._detectar_campo_ref_pago(client)
            previos = client.call(
                "account.payment",
                "search",
                [[[campo_ref, "ilike", tag]]],
                {"limit": 1},
            )
            if previos:
                existente = previos[0]
                pago_existente_id = int(existente["id"]) if isinstance(existente, dict) else int(existente)
                return str(pago_existente_id)

            moneda_id = datos.get("moneda_id")
            if not moneda_id and datos.get("moneda"):
                codigo_mon = str(datos["moneda"]).strip().upper()
                for cur in client.get_monedas() or []:
                    if str(cur.get("name") or "").strip().upper() == codigo_mon:
                        moneda_id = cur.get("id")
                        break

            vals: dict[str, Any] = {
                "partner_id": partner_id,
                # Conversión intencional en la frontera XML-RPC hacia Odoo (amount es Float).
                "amount": float(monto_dec),
                "payment_type": "inbound" if es_cliente else "outbound",
                "partner_type": "customer" if es_cliente else "supplier",
                "journal_id": journal_id,
                campo_ref: memo_final,
            }
            if fecha:
                vals["date"] = fecha
            if moneda_id:
                vals["currency_id"] = int(moneda_id)

            created = client.call("account.payment", "create", [vals])
            pago_id = int(created[0]) if isinstance(created, list) else int(created)

            if modo == "confirmado":
                client.call("account.payment", "action_post", [[pago_id]])
                if facturas_odoo_ids:
                    self._conciliar_pago_con_facturas(client, pago_id, facturas_odoo_ids)

            return str(pago_id)
        except OdooAuthError as exc:
            raise ConnectorConnectionError(self._sanitizar_error_externo(exc)) from None
        except OdooCallError as exc:
            raise ConnectorDataError(self._sanitizar_error_externo(exc)) from None

    def push_gestion_cobranza(self, datos: dict) -> str:
        """Publica una gestión de cobranza en Odoo (account.move o res.partner) de forma idempotente y XSS-safe."""
        factura_id = datos.get("factura_odoo_id")
        partner_id = datos.get("partner_id")

        if factura_id not in (None, "", False) and not isinstance(factura_id, bool):
            try:
                res_id = int(factura_id)
            except (TypeError, ValueError) as exc:
                raise ConnectorDataError("push_gestion_cobranza: factura_odoo_id inválido.") from exc
            model = "account.move"
        elif partner_id not in (None, "", False) and not isinstance(partner_id, bool):
            try:
                res_id = int(partner_id)
            except (TypeError, ValueError) as exc:
                raise ConnectorDataError("push_gestion_cobranza: partner_id inválido.") from exc
            model = "res.partner"
        else:
            raise ConnectorDataError("push_gestion_cobranza requiere 'factura_odoo_id' o 'partner_id'.")

        if res_id <= 0:
            raise ConnectorDataError("push_gestion_cobranza: el ID destino en Odoo debe ser mayor que cero.")

        raw_key = str(datos.get("idempotency_key") or datos.get("id_omni") or "").strip()
        if not raw_key:
            seed = "|".join(
                [
                    model,
                    str(res_id),
                    str(datos.get("fecha_gestion") or ""),
                    str(datos.get("canal") or ""),
                    str(datos.get("resultado") or ""),
                    str(datos.get("notas") or ""),
                ]
            )
            raw_key = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        tag = f"[OMNI-GESTION:{raw_key}]"

        canal_esc = html.escape(str(datos.get("canal") or ""), quote=True)
        resultado_esc = html.escape(str(datos.get("resultado") or ""), quote=True)
        notas_esc = html.escape(str(datos.get("notas") or ""), quote=True)
        orden_ref_esc = html.escape(str(datos.get("orden_ref") or ""), quote=True)
        cliente_esc = html.escape(str(datos.get("cliente_nombre") or ""), quote=True)
        fecha_esc = html.escape(str(datos.get("fecha_gestion") or ""), quote=True)
        proxima_esc = html.escape(str(datos.get("proxima_accion") or ""), quote=True)
        tag_esc = html.escape(tag, quote=True)

        partes_html = [
            f"<p><strong>Gestión de Cobranza ({canal_esc or 'N/A'})</strong> — Resultado: <em>{resultado_esc or 'N/A'}</em></p>",
        ]
        detalles = []
        if cliente_esc:
            detalles.append(f"<li><strong>Cliente:</strong> {cliente_esc}</li>")
        if orden_ref_esc:
            detalles.append(f"<li><strong>Referencia:</strong> {orden_ref_esc}</li>")
        if fecha_esc:
            detalles.append(f"<li><strong>Fecha gestión:</strong> {fecha_esc}</li>")
        if proxima_esc:
            detalles.append(f"<li><strong>Próxima acción:</strong> {proxima_esc}</li>")
        if notas_esc:
            detalles.append(f"<li><strong>Notas:</strong> {notas_esc}</li>")
        if detalles:
            partes_html.append(f"<ul>{''.join(detalles)}</ul>")
        partes_html.append(f"<p><small>{tag_esc}</small></p>")
        body_html = "".join(partes_html)

        client = self._get_write_client()
        try:
            previos = client.call(
                "mail.message",
                "search",
                [[["model", "=", model], ["res_id", "=", res_id], ["body", "ilike", tag]]],
                {"limit": 1},
            )
            if previos:
                existente = previos[0]
                msg_id = int(existente["id"]) if isinstance(existente, dict) else int(existente)
                return str(msg_id)

            posted = client.call(
                model,
                "message_post",
                [[res_id]],
                {
                    "body": body_html,
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_note",
                },
            )
            if isinstance(posted, dict):
                msg_id = int(posted["id"])
            elif isinstance(posted, list):
                msg_id = int(posted[0])
            else:
                msg_id = int(posted)
            return str(msg_id)
        except OdooAuthError as exc:
            raise ConnectorConnectionError(self._sanitizar_error_externo(exc)) from None
        except OdooCallError as exc:
            raise ConnectorDataError(self._sanitizar_error_externo(exc)) from None

    def push_producto(self, datos: dict) -> str:
        """Crea o actualiza un producto en Odoo."""
        client = (
            self._get_write_client()
            if (getattr(self, "_config", None) or {}).get("push_habilitado")
            else self._get_client()
        )
        id_externo = datos.get("id_externo")

        vals = {}
        if datos.get("nombre"):
            vals["name"] = datos["nombre"]
        if datos.get("codigo_interno"):
            vals["default_code"] = datos["codigo_interno"]
        # BUG-NEW-3: conversión de borde hacia Odoo. XML-RPC no soporta Decimal y
        # los campos list_price/standard_price de Odoo son Float; este float() es una
        # conversión intencional en la frontera del sistema externo, no cálculo
        # monetario interno (que sí usa Decimal — R-CODE-4).
        if datos.get("precio_venta") is not None:
            vals["list_price"] = float(datos["precio_venta"])
        if datos.get("costo") is not None:
            vals["standard_price"] = float(datos["costo"])
        if datos.get("descripcion_venta"):
            vals["description_sale"] = datos["descripcion_venta"]

        if id_externo:
            client.actualizar_producto(int(id_externo), vals)
            return id_externo
        else:
            nuevo_id = client.crear_producto(vals)
            return str(nuevo_id)

    def _instancia_persistida(self) -> bool:
        from apps.integration_hub.models import ConectorInstancia

        inst = getattr(self, "instancia", None)
        return isinstance(inst, ConectorInstancia) and bool(inst.pk)

    def _resolver_datos_lead_push(self, evento_o_datos: Any) -> dict[str, Any]:
        """Normaliza entrada de ``push_lead`` (``EventoOutbox`` o ``dict``) enriqueciendo con ``crm.Lead``."""
        from apps.crm.models import Lead
        from apps.integration_hub.models import EventoOutbox

        if isinstance(evento_o_datos, EventoOutbox):
            tipo_evento = str(evento_o_datos.tipo_evento or "").strip()
            payload = dict(evento_o_datos.payload or {})
            lead_id_str = str(evento_o_datos.entidad_id or payload.get("lead_id") or "").strip()
        elif isinstance(evento_o_datos, dict):
            payload = dict(evento_o_datos)
            tipo_evento = str(payload.get("tipo_evento") or "crm.lead.capturado").strip()
            lead_id_str = str(payload.get("lead_id") or payload.get("id_lead") or "").strip()
        else:
            raise ConnectorDataError("push_lead requiere un EventoOutbox o un diccionario de datos.")

        if not lead_id_str:
            raise ConnectorDataError("push_lead requiere 'lead_id'.")

        lead_obj: Lead | None = None
        if self._instancia_persistida():
            try:
                lead_uuid = uuid.UUID(lead_id_str)
            except (ValueError, TypeError):
                lead_uuid = None
            if lead_uuid is not None:
                lead_obj = (
                    Lead.objects.select_related("etapa", "pipeline")
                    .filter(pk=lead_uuid, id_empresa_id=self.instancia.id_empresa_id)
                    .first()
                )

        es_anonimizado = (
            tipo_evento == "crm.lead.anonimizado"
            or bool(payload.get("anonimizado") is True)
            or bool(lead_obj is not None and lead_obj.anonimizado)
        )

        if lead_obj is not None and not es_anonimizado:
            return {
                "tipo_evento": tipo_evento,
                "lead_id": lead_id_str,
                "anonimizado": False,
                "nombre": lead_obj.nombre or "",
                "apellido": lead_obj.apellido or "",
                "empresa_nombre": lead_obj.empresa_nombre or "",
                "email": lead_obj.email or "",
                "telefono": lead_obj.telefono or "",
                "mensaje": lead_obj.mensaje or "",
                "fuente": lead_obj.fuente or "",
                "etapa_id": str(lead_obj.etapa_id) if lead_obj.etapa_id else "",
                "etapa_nombre": lead_obj.etapa.nombre if lead_obj.etapa_id else "",
                "pipeline_nombre": lead_obj.pipeline.nombre if lead_obj.pipeline_id else "",
                "cliente_id": str(lead_obj.cliente_convertido_id)
                if lead_obj.cliente_convertido_id
                else str(payload.get("cliente_id") or ""),
                "odoo_lead_id": payload.get("odoo_lead_id"),
            }

        return {
            "tipo_evento": tipo_evento,
            "lead_id": lead_id_str,
            "anonimizado": es_anonimizado,
            "nombre": str(payload.get("nombre") or "").strip(),
            "apellido": str(payload.get("apellido") or "").strip(),
            "empresa_nombre": str(payload.get("empresa_nombre") or "").strip(),
            "email": str(payload.get("email") or "").strip(),
            "telefono": str(payload.get("telefono") or "").strip(),
            "mensaje": str(payload.get("mensaje") or "").strip(),
            "fuente": str(payload.get("fuente") or "").strip(),
            "etapa_id": str(payload.get("etapa_id") or "").strip(),
            "etapa_nombre": str(payload.get("etapa_nombre") or "").strip(),
            "pipeline_nombre": str(payload.get("pipeline_nombre") or "").strip(),
            "cliente_id": str(payload.get("cliente_id") or "").strip(),
            "odoo_lead_id": payload.get("odoo_lead_id"),
        }

    def _construir_vals_crm_lead(self, datos: dict[str, Any]) -> dict[str, Any]:
        """Construye diccionario de campos exclusivamente para ``crm.lead`` (NUNCA ``res.partner``)."""
        if datos["anonimizado"]:
            return {
                "name": "Contacto anonimizado",
                "contact_name": "",
                "email_from": False,
                "phone": False,
                "partner_name": False,
                "description": "Anonimizado por solicitud de privacidad",
            }

        nombre_completo = f"{datos['nombre']} {datos['apellido']}".strip()
        empresa_nombre = datos["empresa_nombre"]
        if nombre_completo and empresa_nombre:
            titulo = f"{nombre_completo} — {empresa_nombre}"
        else:
            titulo = nombre_completo or empresa_nombre or f"Lead Omni {datos['lead_id'][:8]}"

        lineas_desc = [f"[OMNI-LEAD:{datos['lead_id']}]"]
        if datos["fuente"]:
            lineas_desc.append(f"Fuente: {datos['fuente']}")
        if datos["pipeline_nombre"]:
            lineas_desc.append(f"Pipeline: {datos['pipeline_nombre']}")
        if datos["etapa_nombre"]:
            lineas_desc.append(f"Etapa: {datos['etapa_nombre']}")
        if datos["tipo_evento"] == "crm.lead.convertido" and datos["cliente_id"]:
            lineas_desc.append(f"Convertido a cliente Omni: {datos['cliente_id']}")
        if datos["mensaje"]:
            lineas_desc.append(f"Mensaje: {datos['mensaje']}")

        vals: dict[str, Any] = {
            "name": titulo,
            "description": "\n".join(lineas_desc),
        }
        if nombre_completo:
            vals["contact_name"] = nombre_completo
        if empresa_nombre:
            vals["partner_name"] = empresa_nombre
        if datos["email"]:
            vals["email_from"] = datos["email"]
        if datos["telefono"]:
            vals["phone"] = datos["telefono"]

        cfg = getattr(self, "_config", None) or {}
        mapa_etapas = cfg.get("mapa_etapas_odoo")
        if isinstance(mapa_etapas, dict):
            stage_raw = mapa_etapas.get(datos["etapa_id"])
            if stage_raw is None and datos["etapa_nombre"]:
                stage_raw = mapa_etapas.get(datos["etapa_nombre"])
            stage_id = OdooXMLRPCClient._m2o_id(stage_raw)
            if stage_id is not None:
                vals["stage_id"] = stage_id

        return vals

    def push_lead(self, evento_o_datos: Any) -> dict[str, Any]:
        """Empuja o actualiza un lead Connect hacia ``crm.lead`` en Odoo de forma idempotente.

        Reglas estrictas:
        - Opt-in obligatorio ``empujar_connect_leads=True`` + credenciales de escritura
          ``write_user``/``write_api_key`` (fail-closed).
        - Opera EXCLUSIVAMENTE sobre ``crm.lead`` (NUNCA crea/actualiza ``res.partner``).
        - Idempotente vía ``EntidadSincronizada`` (``tipo_entidad='crm_lead'``):
          create la primera vez, update en eventos posteriores.
        - Ante ``crm.lead.anonimizado``: limpia PII en Odoo si ya existía mapeo;
          si nunca fue empujado, NO crea registro nuevo.
        """
        from apps.integration_hub.models import EntidadSincronizada

        client = self._get_connect_lead_write_client()
        datos = self._resolver_datos_lead_push(evento_o_datos)
        lead_id = datos["lead_id"]

        mapeo: EntidadSincronizada | None = None
        if self._instancia_persistida():
            mapeo = (
                EntidadSincronizada.objects.filter(
                    id_instancia=self.instancia,
                    tipo_entidad="crm_lead",
                    id_omni=lead_id,
                    activo=True,
                )
                .order_by("-ultimo_sync")
                .first()
            )

        odoo_lead_id: int | None = None
        if mapeo is not None:
            odoo_lead_id = OdooXMLRPCClient._m2o_id(mapeo.id_externo)
        elif datos.get("odoo_lead_id") is not None:
            odoo_lead_id = OdooXMLRPCClient._m2o_id(datos.get("odoo_lead_id"))

        try:
            if datos["anonimizado"]:
                if odoo_lead_id is None:
                    return {
                        "accion": "omitido",
                        "odoo_lead_id": None,
                        "lead_id": lead_id,
                        "motivo": "lead_no_sincronizado",
                    }
                vals_anon = self._construir_vals_crm_lead(datos)
                client.actualizar_lead_crm(odoo_lead_id, vals_anon)
                if mapeo is not None:
                    mapeo.checksum = self._checksum(vals_anon)
                    mapeo.metadatos = {
                        **(mapeo.metadatos or {}),
                        "anonimizado": True,
                        "ultimo_evento": datos["tipo_evento"],
                    }
                    mapeo.save(update_fields=["checksum", "metadatos", "ultimo_sync"])
                return {
                    "accion": "anonimizado",
                    "odoo_lead_id": odoo_lead_id,
                    "lead_id": lead_id,
                }

            vals = self._construir_vals_crm_lead(datos)
            checksum = self._checksum(vals)

            if odoo_lead_id is None and hasattr(client, "buscar_lead_crm_por_tag"):
                encontrado = client.buscar_lead_crm_por_tag(f"[OMNI-LEAD:{lead_id}]")
                if isinstance(encontrado, int) and not isinstance(encontrado, bool) and encontrado > 0:
                    odoo_lead_id = encontrado

            if odoo_lead_id is not None:
                client.actualizar_lead_crm(odoo_lead_id, vals)
                accion = "actualizado"
            else:
                odoo_lead_id = int(client.crear_lead_crm(vals))
                accion = "creado"

            if self._instancia_persistida():
                EntidadSincronizada.objects.update_or_create(
                    id_instancia=self.instancia,
                    tipo_entidad="crm_lead",
                    id_externo=str(odoo_lead_id),
                    defaults={
                        "id_omni": lead_id,
                        "modelo_omni": "apps.crm.models.Lead",
                        "checksum": checksum,
                        "metadatos": {
                            "ultimo_evento": datos["tipo_evento"],
                            "etapa_id": datos["etapa_id"],
                        },
                        "activo": True,
                    },
                )

            return {
                "accion": accion,
                "odoo_lead_id": odoo_lead_id,
                "lead_id": lead_id,
            }
        except OdooAuthError as exc:
            raise ConnectorConnectionError(self._sanitizar_error_externo(exc)) from None
        except OdooCallError as exc:
            raise ConnectorDataError(self._sanitizar_error_externo(exc)) from None

    # ── Utilidades ────────────────────────────────────────────────────────────

    @staticmethod
    def _checksum(data: dict) -> str:
        """
        Calcula checksum SHA-256 de un dict para detección de cambios.
        Excluye campos de metadata (write_date, etc.) que cambian siempre.
        """
        exclude = {"write_date", "create_date", "__last_update"}
        clean = {k: v for k, v in data.items() if k not in exclude}
        serialized = json.dumps(clean, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    # ── Cartera / CxC ─────────────────────────────────────────────────────────

    def _odoo_base_url(self, config) -> str:
        """
        M-SEC-2: resuelve y valida la URL base de Odoo. Exige https:// en
        producción (DEBUG=False) para no enviar credenciales XML-RPC en claro.
        """
        url = normalize_odoo_host(config.get("url") or config.get("host") or "")
        from django.conf import settings

        if not url.startswith("https://") and not getattr(settings, "DEBUG", False):
            raise ConnectorConnectionError("La URL de Odoo debe usar https:// en producción (M-SEC-2).")
        return url

    def pull_cartera_vencida(self, desde=None, solo_vencidas=True) -> list[dict]:
        """
        Obtiene cartera vencida desde Odoo.
        Portado de GestionCxC/backend/odoo_client.py → get_ventas_extendidas().

        Normaliza a formato canónico Omni con keys:
        cliente_id, cliente_nombre, orden_ref, monto_total, monto_pendiente,
        fecha_vencimiento, fecha_entrega, estado_pago, dias_termino,
        dias_vencida, vencida, bucket
        """
        from datetime import date as date_cls
        from datetime import datetime
        import xmlrpc.client  # nosec B411

        try:
            config = self._config
            url = self._odoo_base_url(config)
            db = config.get("db", "")
            uid = config.get("uid") or config.get("user")
            password = config.get("password", "") or config.get("api_key", "")

            models_proxy = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

            domain = [["state", "in", ["sale", "done"]]]
            if solo_vencidas:
                domain.append(["payment_term_id", "!=", False])

            fields = [
                "partner_id",
                "name",
                "amount_total",
                "amount_residual",
                "invoice_date_due",
                "commitment_date",
                "invoice_payment_state",
                "payment_term_id",
                "date_order",
            ]

            # Intentar con account.move (facturas) primero, luego sale.order
            try:
                records = models_proxy.execute_kw(
                    db,
                    uid,
                    password,
                    "account.move",
                    "search_read",
                    [domain],
                    {"fields": fields, "limit": 500},
                )
            except Exception:
                records = []

            hoy = date_cls.today()
            resultado = []
            for rec in records:
                fecha_vcto = None
                if rec.get("invoice_date_due"):
                    try:
                        fecha_vcto = datetime.strptime(rec["invoice_date_due"], "%Y-%m-%d").date()
                    except Exception:
                        pass

                # M-BUG-15: distinguir "al día" (0) de "fecha inválida/ausente" (None).
                if fecha_vcto:
                    dias_vencida = (hoy - fecha_vcto).days
                    vencida = dias_vencida > 0
                else:
                    dias_vencida = None
                    vencida = False

                if solo_vencidas and not vencida:
                    continue

                monto_total = self._safe_decimal(rec.get("amount_total", 0))
                monto_pendiente = self._safe_decimal(rec.get("amount_residual", 0))

                resultado.append(
                    {
                        "cliente_id": str(rec["partner_id"][0]) if rec.get("partner_id") else "",
                        "cliente_nombre": self._safe_str(rec.get("partner_id"), "partner"),
                        "orden_ref": self._safe_str(rec.get("name"), "ref"),
                        "monto_total": monto_total,
                        "monto_pendiente": monto_pendiente,
                        "fecha_vencimiento": fecha_vcto.isoformat() if fecha_vcto else None,
                        "fecha_entrega": rec.get("commitment_date"),
                        "estado_pago": self._safe_str(rec.get("invoice_payment_state"), "estado"),
                        "dias_termino": 0,
                        "dias_vencida": dias_vencida,
                        "vencida": vencida,
                        "bucket": self._aging_bucket(dias_vencida) if dias_vencida is not None else "sin_fecha",
                    }
                )

            return resultado

        except Exception as exc:
            raise ConnectorConnectionError(f"Error obteniendo cartera Odoo: {exc}") from exc

    def pull_pagos_cliente(self, partner_id: str) -> list[dict]:
        """Pagos normalizados de un cliente específico desde Odoo."""
        import xmlrpc.client  # nosec B411

        try:
            config = self._config
            url = self._odoo_base_url(config)
            db = config.get("db", "")
            uid = config.get("uid") or config.get("user")
            password = config.get("password", "") or config.get("api_key", "")

            models_proxy = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

            records = models_proxy.execute_kw(
                db,
                uid,
                password,
                "account.payment",
                "search_read",
                [[["partner_id", "=", int(partner_id)], ["state", "=", "posted"]]],
                {
                    "fields": [
                        "name",
                        "date",
                        "amount",
                        "currency_id",
                        "payment_type",
                        "ref",
                    ],
                    "limit": 100,
                },
            )

            return [
                {
                    "pago_id": str(rec.get("id", "")),
                    "referencia": self._safe_str(rec.get("name")),
                    "fecha": rec.get("date"),
                    "monto": self._safe_decimal(rec.get("amount", 0)),
                    "moneda": self._safe_str(rec.get("currency_id")),
                    "tipo": self._safe_str(rec.get("payment_type")),
                    "nota": self._safe_str(rec.get("ref")),
                }
                for rec in records
            ]

        except Exception as exc:
            raise ConnectorConnectionError(f"Error obteniendo pagos cliente {partner_id}: {exc}") from exc

    @staticmethod
    def _aging_bucket(dias: int) -> str:
        """Clasifica en bucket de aging por días vencido."""
        if dias <= 0:
            return "al_dia"
        if dias <= 30:
            return "1_30"
        if dias <= 60:
            return "31_60"
        if dias <= 90:
            return "61_90"
        return "mas_90"

    @staticmethod
    def _term_days_map(term_name: str) -> int:
        """Extrae días numéricos de nombre de término de pago con regex fallback."""
        import re

        if not term_name:
            return 0
        m = re.search(r"(\d+)", str(term_name))
        return int(m.group(1)) if m else 0
