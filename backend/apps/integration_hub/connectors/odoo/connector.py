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
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

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
        "pagos",
        "inventario",
    ]

    def __init__(self, instancia: "ConectorInstancia"):
        super().__init__(instancia)
        self._client: OdooXMLRPCClient | None = None

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
            raise ConnectorConnectionError(str(exc)) from exc

        return self._client

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

    def pull_contactos(
        self, desde: datetime | None = None, limite: int = 500
    ) -> list[dict]:
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
            "pais_codigo": (country[1] if isinstance(country, list) and len(country) > 1
                            else str(country) if country else ""),
            "pais_nombre": (country[1] if isinstance(country, list) and len(country) > 1
                            else ""),
            "estado_provincia": (state[1] if isinstance(state, list) and len(state) > 1
                                 else ""),
            "empresa_padre_id": (str(parent[0]) if isinstance(parent, list) and parent
                                  else ""),
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

    def pull_productos(
        self, desde: datetime | None = None, limite: int = 500
    ) -> list[dict]:
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
            "categoria_nombre": (categ[1] if isinstance(categ, list) and len(categ) > 1
                                 else ""),
            "unidad_medida": (uom[1] if isinstance(uom, list) and len(uom) > 1 else ""),
            "unidad_compra": (uom_po[1] if isinstance(uom_po, list) and len(uom_po) > 1
                              else ""),
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

    def pull_pedidos_venta(
        self, desde: datetime | None = None, limite: int = 200
    ) -> list[dict]:
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
            "cliente_nombre": (partner[1] if isinstance(partner, list) and len(partner) > 1
                               else ""),
            "vendedor_nombre": (user[1] if isinstance(user, list) and len(user) > 1 else ""),
            "fecha_pedido": (raw.get("date_order") or "")[:10],
            "estado": estado_map.get(raw.get("state") or "", raw.get("state") or ""),
            "estado_factura": factura_map.get(
                raw.get("invoice_status") or "", raw.get("invoice_status") or ""
            ),
            "subtotal": self._safe_decimal(raw.get("amount_untaxed")),
            "impuestos": self._safe_decimal(raw.get("amount_tax")),
            "total": self._safe_decimal(raw.get("amount_total")),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1
                       else "USD"),
            "lista_precios": (pricelist[1] if isinstance(pricelist, list) and len(pricelist) > 1
                              else ""),
            "termino_pago": (payment_term[1]
                             if isinstance(payment_term, list) and len(payment_term) > 1
                             else ""),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Pedidos de Compra ─────────────────────────────────────────────────────

    def pull_pedidos_compra(
        self, desde: datetime | None = None, limite: int = 200
    ) -> list[dict]:
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
            "proveedor_nombre": (partner[1] if isinstance(partner, list) and len(partner) > 1
                                 else ""),
            "fecha_pedido": (raw.get("date_order") or "")[:10],
            "fecha_aprobacion": (raw.get("date_approve") or "")[:10],
            "estado": raw.get("state") or "",
            "estado_factura": raw.get("invoice_status") or "",
            "subtotal": self._safe_decimal(raw.get("amount_untaxed")),
            "impuestos": self._safe_decimal(raw.get("amount_tax")),
            "total": self._safe_decimal(raw.get("amount_total")),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1
                       else "USD"),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Facturas de Venta ─────────────────────────────────────────────────────

    def pull_facturas_venta(
        self, desde: datetime | None = None, limite: int = 200
    ) -> list[dict]:
        """Trae facturas de venta publicadas de Odoo."""
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d %H:%M:%S") if desde else None

        try:
            facturas = client.get_facturas(tipo="out_invoice", desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo facturas de Odoo: {exc}") from exc

        return [self._normalizar_factura(f) for f in facturas]

    def _normalizar_factura(self, raw: dict) -> dict:
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
            "cliente_id_externo": str(partner[0]) if isinstance(partner, list) and partner else "",
            "cliente_nombre": (partner[1] if isinstance(partner, list) and len(partner) > 1
                               else ""),
            "fecha_factura": (raw.get("invoice_date") or "")[:10],
            "fecha_vencimiento": (raw.get("invoice_date_due") or "")[:10],
            "subtotal": self._safe_decimal(raw.get("amount_untaxed")),
            "impuestos": self._safe_decimal(raw.get("amount_tax")),
            "total": self._safe_decimal(raw.get("amount_total")),
            "saldo_pendiente": self._safe_decimal(raw.get("amount_residual")),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1
                       else "USD"),
            "estado_pago": pago_estado_map.get(
                raw.get("payment_state") or "", raw.get("payment_state") or ""
            ),
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Pagos ─────────────────────────────────────────────────────────────────

    def pull_pagos(
        self, desde: datetime | None = None, limite: int = 300
    ) -> list[dict]:
        """Trae pagos (inbound + outbound) de Odoo."""
        client = self._get_client()
        desde_str = desde.strftime("%Y-%m-%d") if desde else None

        try:
            pagos = client.get_pagos(desde=desde_str, limite=limite)
        except OdooCallError as exc:
            raise ConnectorDataError(f"Error leyendo pagos de Odoo: {exc}") from exc

        return [self._normalizar_pago(p) for p in pagos]

    def _normalizar_pago(self, raw: dict) -> dict:
        partner = raw.get("partner_id") or []
        journal = raw.get("journal_id") or []
        currency = raw.get("currency_id") or []

        return {
            "id_externo": str(raw["id"]),
            "numero": raw.get("name") or "",
            "tipo": raw.get("payment_type") or "",  # inbound | outbound
            "tipo_socio": raw.get("partner_type") or "",  # customer | supplier
            "socio_id_externo": str(partner[0]) if isinstance(partner, list) and partner else "",
            "socio_nombre": (partner[1] if isinstance(partner, list) and len(partner) > 1
                             else ""),
            "monto": self._safe_decimal(raw.get("amount")),
            "fecha": (raw.get("date") or "")[:10],
            "estado": raw.get("state") or "",
            "diario": (journal[1] if isinstance(journal, list) and len(journal) > 1 else ""),
            "moneda": (currency[1] if isinstance(currency, list) and len(currency) > 1
                       else "USD"),
            "referencia": raw.get("memo") or raw.get("ref") or "",
            "fecha_modificacion_externo": (raw.get("write_date") or "")[:19],
            "_checksum": self._checksum(raw),
            "_fuente": "odoo",
        }

    # ── Inventario ────────────────────────────────────────────────────────────

    def pull_inventario(
        self, desde: datetime | None = None, limite: int = 500
    ) -> list[dict]:
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
            "producto_nombre": (product[1] if isinstance(product, list) and len(product) > 1
                                else ""),
            "ubicacion_id_externo": str(location[0]) if isinstance(location, list) and location else "",
            "ubicacion_nombre": (location[1] if isinstance(location, list) and len(location) > 1
                                 else ""),
            "cantidad": self._safe_float(raw.get("quantity")),
            "cantidad_reservada": self._safe_float(raw.get("reserved_quantity")),
            "cantidad_disponible": max(
                0.0,
                self._safe_float(raw.get("quantity")) - self._safe_float(raw.get("reserved_quantity"))
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
        client = self._get_client()
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

        if id_externo:
            client.actualizar_socio(int(id_externo), vals)
            return id_externo
        else:
            nuevo_id = client.crear_socio(vals)
            return str(nuevo_id)

    def push_producto(self, datos: dict) -> str:
        """Crea o actualiza un producto en Odoo."""
        client = self._get_client()
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
        url = (config.get("url") or config.get("host") or "").rstrip("/")
        from django.conf import settings

        if not url.startswith("https://") and not getattr(settings, "DEBUG", False):
            raise ConnectorConnectionError(
                "La URL de Odoo debe usar https:// en producción (M-SEC-2)."
            )
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
                "partner_id", "name", "amount_total",
                "amount_residual", "invoice_date_due",
                "commitment_date", "invoice_payment_state",
                "payment_term_id", "date_order",
            ]

            # Intentar con account.move (facturas) primero, luego sale.order
            try:
                records = models_proxy.execute_kw(
                    db, uid, password,
                    "account.move", "search_read",
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

                resultado.append({
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
                })

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
                db, uid, password,
                "account.payment", "search_read",
                [[["partner_id", "=", int(partner_id)], ["state", "=", "posted"]]],
                {"fields": ["name", "date", "amount", "currency_id", "payment_type", "ref"], "limit": 100},
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
