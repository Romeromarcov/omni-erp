"""
Migrador 1-Click Odoo (SOLO LECTURA) + Saint / Profit / Galac CSV (Plan 09 Fase 8.4).

Reglas críticas:
  - Odoo: estrictamente SOLO LECTURA (`ALLOWED_ODOO_METHODS`). Cualquier intento de
    invocar `create`, `write`, `unlink`, `action_*` u otro método fuera de la whitelist
    lanza `MigracionReadOnlyError`.
  - Aislamiento multi-tenant: las credenciales de Odoo se resuelven siempre desde
    `integration_hub.ConectorInstancia` filtrada por `id_empresa`; nunca se aceptan
    hosts/credenciales arbitrarios por HTTP ni se loguean secretos (`R-CODE-8`).
  - Idempotencia por entidad en upsert + `ProcesoMigracion` + `DetalleErrorMigracion`
    sobre las tablas existentes cubiertas por RLS (`0001_initial`).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import io
import re
from typing import Any
import unicodedata
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.almacenes.models import Almacen
from apps.contabilidad.models import PlanCuentas
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.finanzas.models import Moneda
from apps.integration_hub.connectors.odoo.client import OdooAuthError, OdooCallError, OdooXMLRPCClient
from apps.integration_hub.models import ConectorInstancia
from apps.inventario.models import CategoriaProducto, Producto, StockActual, UnidadMedida
from apps.migracion_datos.models import DetalleErrorMigracion, PlantillaMigracion, ProcesoMigracion
from apps.proveedores.models import Proveedor

ALLOWED_ODOO_METHODS: frozenset[str] = frozenset(
    {
        "search_read",
        "read",
        "search_count",
        "read_group",
        "fields_get",
    }
)

FUENTES_SOPORTADAS: tuple[str, ...] = ("ODOO", "SAINT", "PROFIT", "GALAC", "OMNI_CSV")
ENTIDADES_SOPORTADAS: tuple[str, ...] = ("plan_cuentas", "contactos", "productos", "stock", "cxc_cxp")

_LIMITE_MAX = 2000

COLUMN_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "plan_cuentas": {
        "codigo_cuenta": ("codigo_cuenta", "codcta", "co_cue", "codigo", "code", "cuenta", "nro_cuenta"),
        "nombre_cuenta": ("nombre_cuenta", "descrip", "descripcion", "des_cue", "nombre", "name"),
        "tipo_cuenta": ("tipo_cuenta", "tipo", "account_type", "clase", "grupo"),
        "naturaleza": ("naturaleza", "saldo_normal", "signo", "dc"),
        "nivel": ("nivel", "level", "grado"),
        "codigo_padre": ("codigo_padre", "padre", "cuenta_padre", "cod_padre"),
        "activo": ("activo", "active", "habilitada"),
    },
    "contactos": {
        "razon_social": (
            "razon_social",
            "descrip",
            "cli_des",
            "prov_des",
            "nombre",
            "name",
            "cliente",
            "proveedor",
        ),
        "rif": ("rif", "nit", "vat", "id_fiscal", "cedula_rif", "co_rif"),
        "nombre_comercial": ("nombre_comercial", "alias", "representante", "repr"),
        "direccion": ("direccion", "direc1", "dir", "street", "domicilio"),
        "telefono": ("telefono", "telef", "tlf", "phone", "mobile", "celular"),
        "email": ("email", "correo", "e_mail", "mail"),
        "rol": ("rol", "role", "tipo_tercero", "perfil"),
        "tipo_cliente": ("tipo_cliente", "condicion_pago", "tipo"),
        "limite_credito": ("limite_credito", "limitecred", "montocred", "credit_limit"),
        "dias_credito": ("dias_credito", "diascred", "plazo", "credit_days"),
    },
    "productos": {
        "sku": ("sku", "codprod", "co_art", "codigo", "default_code", "referencia"),
        "nombre_producto": ("nombre_producto", "descrip", "art_des", "name", "nombre", "descripcion"),
        "categoria": ("categoria", "codinst", "lin_des", "linea", "categ_id", "grupo"),
        "unidad_medida": ("unidad_medida", "unidad", "co_uni", "uom", "uom_id"),
        "moneda": ("moneda", "codigo_moneda", "currency", "co_mone"),
        "tipo_producto": ("tipo_producto", "tipo", "type"),
        "costo_promedio": ("costo_promedio", "costpro", "cos_un", "standard_price", "costo"),
        "costo_reposicion_usd": ("costo_reposicion_usd", "costo_rep", "costo_usd", "costact"),
        "precio_venta_sugerido": ("precio_venta_sugerido", "precio1", "prec_vta1", "list_price", "precio"),
        "codigo_barras": ("codigo_barras", "barcode", "ean", "codbarra"),
    },
    "stock": {
        "sku": ("sku", "codprod", "co_art", "codigo", "default_code"),
        "almacen": ("almacen", "codubic", "co_alma", "codigo_almacen", "warehouse"),
        "cantidad_disponible": ("cantidad_disponible", "existen", "stock_act", "quantity", "cantidad", "existencia"),
        "cantidad_minima": ("cantidad_minima", "exmin", "pto_min", "minimo"),
        "cantidad_maxima": ("cantidad_maxima", "exmax", "pto_max", "maximo"),
    },
    "cxc_cxp": {
        "tipo": ("tipo", "tipo_doc", "move_type", "origen", "cartera"),
        "rif": ("rif", "rif_cliente", "rif_proveedor", "codclie", "codprov", "co_cli", "co_prov", "vat"),
        "razon_social": ("razon_social", "nombre", "partner_name", "descrip"),
        "referencia_externa": ("referencia_externa", "numerod", "nro_doc", "documento", "name", "ref", "factura"),
        "monto": ("monto", "saldo", "saldo_pendiente", "amount_residual", "monto_pendiente", "total"),
        "fecha_emision": ("fecha_emision", "fechae", "fec_emis", "invoice_date", "fecha"),
        "fecha_vencimiento": ("fecha_vencimiento", "fechav", "fec_venc", "invoice_date_due", "vence"),
        "estado": ("estado", "status"),
        "descripcion": ("descripcion", "notas", "observaciones", "nota"),
    },
}

_SOURCE_HINTS: dict[str, dict[str, str]] = {
    "SAINT": {
        "separador_tipico": ";",
        "campos_clave": "SAACXP/SAACXC/SAPROD/SACLIE (CODPROD, CODCLIE, NUMEROD, RIF, FECHAE, FECHAV)",
    },
    "PROFIT": {
        "separador_tipico": ";",
        "campos_clave": "art/clientes/prov/docum_cc (co_art, art_des, co_cli, co_prov, fec_emis, fec_venc)",
    },
    "GALAC": {
        "separador_tipico": ",",
        "campos_clave": "Plan/Terceros/Inventario/Cartera (Codigo, Descripcion, RIF, Saldo, Vence)",
    },
    "OMNI_CSV": {
        "separador_tipico": ",",
        "campos_clave": "Columnas canónicas directas Omni ERP",
    },
    "ODOO": {
        "separador_tipico": "XML-RPC",
        "campos_clave": "ConectorInstancia read-only (account.account, res.partner, product.template, stock.quant, account.move)",
    },
}


class MigracionError(ValueError):
    """Error controlado del migrador 1-click."""


class MigracionReadOnlyError(MigracionError):
    """Bloqueo estricto ante cualquier intento de escritura sobre Odoo."""


def _normalizar_header(raw: str) -> str:
    limpio = unicodedata.normalize("NFKD", (raw or "").lstrip("\ufeff").strip())
    ascii_only = limpio.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")


def _validar_sin_nul(valor: Any, campo: str = "entrada") -> None:
    if isinstance(valor, str) and "\x00" in valor:
        raise MigracionError(f"El campo '{campo}' contiene bytes NUL inválidos.")


def _normalizar_rif(raw: Any) -> str:
    texto = str(raw or "").strip().upper()
    _validar_sin_nul(texto, "rif")
    compacto = re.sub(r"[\s.]+", "", texto)
    if compacto.startswith("VE") and len(compacto) > 2 and compacto[2] in "VJEGBP":
        compacto = compacto[2:]
    match = re.match(r"^([VJEGBP])[-]?([0-9-]+)$", compacto)
    if match:
        digitos = re.sub(r"[^0-9]", "", match.group(2))
        if digitos:
            return f"{match.group(1)}-{digitos}"
    return compacto


def _a_decimal(raw: Any, campo: str, default: Decimal | None = None) -> Decimal:
    if raw is None or str(raw).strip() == "" or raw is False:
        if default is not None:
            return default
        raise MigracionError(f"El campo numérico '{campo}' es obligatorio.")
    texto = str(raw).strip().replace(" ", "")
    # Soportar formato latinoamericano "1.234,56" además de "1234.56"
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError) as exc:
        raise MigracionError(f"Valor decimal inválido en '{campo}': '{raw}'.") from exc


def _a_fecha(raw: Any, campo: str, default: date | None = None) -> date:
    if raw is None or str(raw).strip() == "" or raw is False:
        if default is not None:
            return default
        raise MigracionError(f"La fecha '{campo}' es obligatoria.")
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    texto = str(raw).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    raise MigracionError(f"Formato de fecha inválido en '{campo}': '{raw}'. Use YYYY-MM-DD o DD/MM/YYYY.")


def _decodificar_csv(contenido: bytes | str) -> str:
    if isinstance(contenido, bytes):
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texto = contenido.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise MigracionError("No se pudo decodificar el archivo CSV (use UTF-8 o Latin-1).")
    else:
        texto = contenido
    _validar_sin_nul(texto, "contenido_csv")
    if not texto.strip():
        raise MigracionError("El contenido CSV está vacío.")
    return texto


def _detectar_delimitador(primera_linea: str) -> str:
    comas = primera_linea.count(",")
    punto_comas = primera_linea.count(";")
    tabs = primera_linea.count("\t")
    if punto_comas >= comas and punto_comas >= tabs and punto_comas > 0:
        return ";"
    if tabs > comas and tabs > punto_comas:
        return "\t"
    return ","


def _parsear_csv_filas(contenido: bytes | str, entidad: str, limite: int) -> list[dict[str, Any]]:
    texto = _decodificar_csv(contenido)
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if not lineas:
        raise MigracionError("El CSV no contiene filas.")
    delimitador = _detectar_delimitador(lineas[0])
    reader = csv.DictReader(io.StringIO("\n".join(lineas)), delimiter=delimitador)
    if not reader.fieldnames:
        raise MigracionError("El CSV no tiene fila de cabecera.")

    alias_map = COLUMN_ALIASES[entidad]
    header_to_canonical: dict[str, str] = {}
    for raw_hdr in reader.fieldnames:
        norm = _normalizar_header(raw_hdr)
        for canon, aliases in alias_map.items():
            if norm == canon or norm in aliases:
                header_to_canonical[raw_hdr] = canon
                break

    filas: list[dict[str, Any]] = []
    for idx, row in enumerate(reader, start=2):
        if len(filas) >= limite:
            break
        canon_row: dict[str, Any] = {"_linea": idx}
        for raw_key, val in row.items():
            if raw_key is None:
                continue
            canon_key = header_to_canonical.get(raw_key)
            if canon_key is None:
                continue
            cleaned = val.strip() if isinstance(val, str) else val
            _validar_sin_nul(cleaned, canon_key)
            if canon_row.get(canon_key) in (None, "") and cleaned not in (None, ""):
                canon_row[canon_key] = cleaned
        filas.append(canon_row)
    return filas


class OdooReadOnlyGuard:
    """Wrapper estricto de solo lectura sobre un cliente XML-RPC de Odoo."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def call(
        self,
        model: str,
        method: str,
        domain: list | None = None,
        kwargs: dict | None = None,
    ) -> Any:
        metodo = str(method or "").strip()
        if metodo not in ALLOWED_ODOO_METHODS:
            raise MigracionReadOnlyError(
                f"Operación Odoo prohibida ('{model}.{metodo}'): el migrador 1-click es estrictamente SOLO LECTURA."
            )
        if hasattr(self._client, "call"):
            return self._client.call(model, metodo, domain, kwargs)
        raise MigracionError("Cliente Odoo incompatible: carece de método call().")

    @staticmethod
    def _m2o_id(val: Any) -> int | None:
        if isinstance(val, (list, tuple)) and val:
            raw = val[0]
        else:
            raw = val
        if isinstance(raw, bool) or raw in (None, "", 0):
            return None
        try:
            parsed = int(raw)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _m2o_name(val: Any) -> str:
        if isinstance(val, (list, tuple)) and len(val) > 1 and val[1]:
            return str(val[1])
        return ""

    def extraer_plan_cuentas(self, limite: int = 500) -> list[dict[str, Any]]:
        registros = (
            self.call(
                "account.account",
                "search_read",
                [[]],
                {"fields": ["id", "code", "name", "account_type", "deprecated"], "limit": limite},
            )
            or []
        )
        return [
            {
                "_linea": idx,
                "codigo_cuenta": rec.get("code") or "",
                "nombre_cuenta": rec.get("name") or "",
                "tipo_cuenta": rec.get("account_type") or "asset_current",
                "activo": not bool(rec.get("deprecated", False)),
            }
            for idx, rec in enumerate(registros, start=1)
        ]

    def extraer_contactos(self, limite: int = 500) -> list[dict[str, Any]]:
        registros = (
            self.call(
                "res.partner",
                "search_read",
                [[["active", "=", True]]],
                {
                    "fields": ["id", "name", "vat", "email", "phone", "street", "customer_rank", "supplier_rank"],
                    "limit": limite,
                },
            )
            or []
        )
        filas: list[dict[str, Any]] = []
        for idx, rec in enumerate(registros, start=1):
            cust = int(rec.get("customer_rank") or 0)
            supp = int(rec.get("supplier_rank") or 0)
            if cust > 0 and supp > 0:
                rol = "AMBOS"
            elif supp > 0:
                rol = "PROVEEDOR"
            else:
                rol = "CLIENTE"
            filas.append(
                {
                    "_linea": idx,
                    "razon_social": rec.get("name") or "",
                    "rif": rec.get("vat") or "",
                    "email": rec.get("email") or "",
                    "telefono": rec.get("phone") or "",
                    "direccion": rec.get("street") or "",
                    "rol": rol,
                }
            )
        return filas

    def extraer_productos(self, limite: int = 500) -> list[dict[str, Any]]:
        registros = (
            self.call(
                "product.template",
                "search_read",
                [[["active", "=", True]]],
                {
                    "fields": [
                        "id",
                        "default_code",
                        "name",
                        "list_price",
                        "standard_price",
                        "categ_id",
                        "uom_id",
                        "type",
                        "barcode",
                    ],
                    "limit": limite,
                },
            )
            or []
        )
        return [
            {
                "_linea": idx,
                "sku": rec.get("default_code") or f"ODOO-{rec.get('id')}",
                "nombre_producto": rec.get("name") or "",
                "categoria": self._m2o_name(rec.get("categ_id")) or "General",
                "unidad_medida": self._m2o_name(rec.get("uom_id")) or "UND",
                "moneda": "USD",
                "tipo_producto": rec.get("type") or "consu",
                "costo_promedio": rec.get("standard_price") or "0",
                "costo_reposicion_usd": rec.get("standard_price") or "0",
                "precio_venta_sugerido": rec.get("list_price") or "0",
                "codigo_barras": rec.get("barcode") or "",
            }
            for idx, rec in enumerate(registros, start=1)
        ]

    def extraer_stock(self, limite: int = 500) -> list[dict[str, Any]]:
        quants = (
            self.call(
                "stock.quant",
                "search_read",
                [[["quantity", ">", 0]]],
                {"fields": ["id", "product_id", "location_id", "quantity", "reserved_quantity"], "limit": limite},
            )
            or []
        )
        prod_ids = sorted({pid for q in quants if (pid := self._m2o_id(q.get("product_id"))) is not None})
        sku_por_id: dict[int, str] = {}
        if prod_ids:
            prods = (
                self.call(
                    "product.product",
                    "search_read",
                    [[["id", "in", prod_ids]]],
                    {"fields": ["id", "default_code"], "limit": len(prod_ids)},
                )
                or []
            )
            for p in prods:
                if p.get("id") and p.get("default_code"):
                    sku_por_id[int(p["id"])] = str(p["default_code"]).strip()

        loc_ids = sorted({lid for q in quants if (lid := self._m2o_id(q.get("location_id"))) is not None})
        almacen_por_loc: dict[int, str] = {}
        if loc_ids:
            locs = (
                self.call(
                    "stock.location",
                    "search_read",
                    [[["id", "in", loc_ids]]],
                    {"fields": ["id", "complete_name", "name"], "limit": len(loc_ids)},
                )
                or []
            )
            for loc in locs:
                if loc.get("id"):
                    almacen_por_loc[int(loc["id"])] = str(loc.get("name") or loc.get("complete_name") or "").strip()

        filas: list[dict[str, Any]] = []
        for idx, q in enumerate(quants, start=1):
            pid = self._m2o_id(q.get("product_id"))
            lid = self._m2o_id(q.get("location_id"))
            prod_name = self._m2o_name(q.get("product_id"))
            sku = sku_por_id.get(pid or -1) or (prod_name.split("]")[0].lstrip("[") if "[" in prod_name else "")
            almacen = almacen_por_loc.get(lid or -1) or self._m2o_name(q.get("location_id"))
            qty = _a_decimal(q.get("quantity") or 0, "quantity", Decimal("0"))
            reserved = _a_decimal(q.get("reserved_quantity") or 0, "reserved_quantity", Decimal("0"))
            disponible = max(Decimal("0"), qty - reserved)
            filas.append(
                {
                    "_linea": idx,
                    "sku": sku,
                    "almacen": almacen,
                    "cantidad_disponible": str(disponible),
                    "cantidad_minima": "0",
                    "cantidad_maxima": "0",
                }
            )
        return filas

    def extraer_cxc_cxp(self, limite: int = 500) -> list[dict[str, Any]]:
        moves = (
            self.call(
                "account.move",
                "search_read",
                [
                    [
                        ["move_type", "in", ["out_invoice", "in_invoice"]],
                        ["state", "=", "posted"],
                        ["payment_state", "in", ["not_paid", "partial"]],
                    ]
                ],
                {
                    "fields": [
                        "id",
                        "name",
                        "move_type",
                        "partner_id",
                        "amount_residual",
                        "invoice_date",
                        "invoice_date_due",
                        "ref",
                    ],
                    "limit": limite,
                },
            )
            or []
        )
        partner_ids = sorted({pid for m in moves if (pid := self._m2o_id(m.get("partner_id"))) is not None})
        vat_por_partner: dict[int, tuple[str, str]] = {}
        if partner_ids:
            partners = (
                self.call(
                    "res.partner",
                    "search_read",
                    [[["id", "in", partner_ids]]],
                    {"fields": ["id", "vat", "name"], "limit": len(partner_ids)},
                )
                or []
            )
            for p in partners:
                if p.get("id"):
                    vat_por_partner[int(p["id"])] = (str(p.get("vat") or ""), str(p.get("name") or ""))

        filas: list[dict[str, Any]] = []
        for idx, m in enumerate(moves, start=1):
            pid = self._m2o_id(m.get("partner_id"))
            vat, p_name = vat_por_partner.get(pid or -1, ("", self._m2o_name(m.get("partner_id"))))
            move_type = str(m.get("move_type") or "out_invoice")
            tipo = "CXP" if move_type == "in_invoice" else "CXC"
            filas.append(
                {
                    "_linea": idx,
                    "tipo": tipo,
                    "rif": vat,
                    "razon_social": p_name,
                    "referencia_externa": m.get("name") or m.get("ref") or f"ODOO-{m.get('id')}",
                    "monto": m.get("amount_residual") or "0",
                    "fecha_emision": m.get("invoice_date") or "",
                    "fecha_vencimiento": m.get("invoice_date_due") or m.get("invoice_date") or "",
                    "estado": "PENDIENTE",
                    "descripcion": m.get("ref") or m.get("name") or "",
                }
            )
        return filas


def construir_guard_desde_conector(empresa: Any, id_conector: str | uuid.UUID) -> OdooReadOnlyGuard:
    """Resuelve una instancia Odoo perteneciente a ``empresa`` y construye un guard SOLO LECTURA."""
    instancia = (
        ConectorInstancia.objects.select_related("id_proveedor")
        .filter(id_empresa=empresa, pk=id_conector, activo=True)
        .first()
    )
    if instancia is None or instancia.id_proveedor.codigo != "odoo":
        raise MigracionError("Conector Odoo no encontrado o inactivo para esta empresa.")

    cfg = instancia.get_config() or {}
    host = str(cfg.get("host") or "").strip()
    db = str(cfg.get("db") or "").strip()
    user = str(cfg.get("user") or "").strip()
    api_key = str(cfg.get("api_key") or "").strip()
    if not (host and db and user and api_key):
        raise MigracionError("El conector Odoo no tiene credenciales de solo lectura completas.")

    try:
        # Intencionalmente NO se pasan write_user ni write_api_key.
        client = OdooXMLRPCClient(host=host, db=db, user=user, api_key=api_key)
    except OdooAuthError as exc:
        raise MigracionError(f"Error autenticando en Odoo (solo lectura): {exc}") from exc
    return OdooReadOnlyGuard(client)


def _mapear_tipo_cuenta(raw: str) -> str:
    val = str(raw or "").strip().lower()
    if val.upper() in {"ACTIVO", "PASIVO", "PATRIMONIO", "INGRESO", "GASTO", "COSTO"}:
        return val.upper()
    if "asset" in val or "receivable" in val or "activo" in val:
        return "ACTIVO"
    if "liability" in val or "payable" in val or "pasivo" in val:
        return "PASIVO"
    if "equity" in val or "patrimonio" in val or "capital" in val:
        return "PATRIMONIO"
    if "income" in val or "ingreso" in val or "venta" in val:
        return "INGRESO"
    if "cost" in val or "costo" in val:
        return "COSTO"
    if "expense" in val or "gasto" in val:
        return "GASTO"
    raise MigracionError(f"tipo_cuenta no reconocido '{raw}'; use ACTIVO/PASIVO/PATRIMONIO/INGRESO/GASTO/COSTO.")


def _mapear_naturaleza(raw: Any, tipo_cuenta: str) -> str:
    txt = str(raw or "").strip().upper()
    if txt in {"DEUDORA", "D", "DEBE", "DEBITO"}:
        return "DEUDORA"
    if txt in {"ACREEDORA", "A", "C", "HABER", "CREDITO"}:
        return "ACREEDORA"
    return "DEUDORA" if tipo_cuenta in {"ACTIVO", "GASTO", "COSTO"} else "ACREEDORA"


def _normalizar_fila(entidad: str, fila: dict[str, Any]) -> dict[str, Any]:
    if entidad == "plan_cuentas":
        codigo = str(fila.get("codigo_cuenta") or "").strip()
        nombre = str(fila.get("nombre_cuenta") or "").strip()
        if not codigo or not nombre:
            raise MigracionError("Plan de cuentas requiere 'codigo_cuenta' y 'nombre_cuenta'.")
        tipo_cuenta = _mapear_tipo_cuenta(str(fila.get("tipo_cuenta") or "ACTIVO"))
        naturaleza = _mapear_naturaleza(fila.get("naturaleza"), tipo_cuenta)
        raw_nivel = fila.get("nivel")
        if raw_nivel not in (None, ""):
            try:
                nivel = max(1, int(str(raw_nivel).strip()))
            except (TypeError, ValueError) as exc:
                raise MigracionError(f"Nivel contable inválido: '{raw_nivel}'.") from exc
        else:
            partes = [p for p in re.split(r"[.\-]", codigo) if p]
            nivel = max(1, len(partes))
        activo_raw = fila.get("activo")
        activo = (
            True
            if activo_raw in (None, "")
            else str(activo_raw).strip().lower() not in {"0", "false", "no", "inactivo"}
        )
        return {
            "codigo_cuenta": codigo[:50],
            "nombre_cuenta": nombre[:255],
            "tipo_cuenta": tipo_cuenta,
            "naturaleza": naturaleza,
            "nivel": nivel,
            "activo": activo,
        }

    if entidad == "contactos":
        razon_social = str(fila.get("razon_social") or "").strip()
        rif = _normalizar_rif(fila.get("rif"))
        if not razon_social or not rif:
            raise MigracionError("Contactos requiere 'razon_social' y 'rif'.")
        rol = str(fila.get("rol") or "CLIENTE").strip().upper()
        if rol not in {"CLIENTE", "PROVEEDOR", "AMBOS"}:
            raise MigracionError(f"Rol de contacto inválido '{rol}'; use CLIENTE, PROVEEDOR o AMBOS.")
        tipo_cliente = str(fila.get("tipo_cliente") or "CONTADO").strip().upper()
        if tipo_cliente not in {"CONTADO", "CREDITO"}:
            tipo_cliente = "CONTADO"
        limite_credito = _a_decimal(fila.get("limite_credito"), "limite_credito", Decimal("0"))
        try:
            dias_credito = max(0, int(fila.get("dias_credito") or 0))
        except (TypeError, ValueError) as exc:
            raise MigracionError(f"dias_credito inválido: '{fila.get('dias_credito')}'.") from exc
        return {
            "razon_social": razon_social[:255],
            "rif": rif[:20],
            "nombre_comercial": str(fila.get("nombre_comercial") or "").strip() or None,
            "direccion": str(fila.get("direccion") or "").strip() or None,
            "telefono": str(fila.get("telefono") or "").strip()[:50] or None,
            "email": str(fila.get("email") or "").strip() or None,
            "rol": rol,
            "tipo_cliente": tipo_cliente,
            "limite_credito": limite_credito,
            "dias_credito": dias_credito,
        }

    if entidad == "productos":
        sku = str(fila.get("sku") or "").strip()
        nombre = str(fila.get("nombre_producto") or "").strip()
        if not sku or not nombre:
            raise MigracionError("Productos requiere 'sku' y 'nombre_producto'.")
        raw_tipo = str(fila.get("tipo_producto") or "PRODUCTO_FISICO").strip().lower()
        if raw_tipo in {"product", "consu", "storable", "consumable", "producto_fisico", "bienes"}:
            tipo_prod = "PRODUCTO_FISICO"
        elif raw_tipo in {"service", "servicio", "servicios"}:
            tipo_prod = "SERVICIO"
        elif raw_tipo in {"kit", "combo"}:
            tipo_prod = raw_tipo.upper()
        else:
            raise MigracionError(f"tipo_producto inválido '{raw_tipo}'.")

        costo = _a_decimal(fila.get("costo_promedio"), "costo_promedio", Decimal("0"))
        costo_rep = _a_decimal(fila.get("costo_reposicion_usd"), "costo_reposicion_usd", costo)
        precio = _a_decimal(fila.get("precio_venta_sugerido"), "precio_venta_sugerido", Decimal("0"))
        return {
            "sku": sku[:100],
            "nombre_producto": nombre[:255],
            "categoria": str(fila.get("categoria") or "General").strip()[:100] or "General",
            "unidad_medida": str(fila.get("unidad_medida") or "UND").strip()[:10] or "UND",
            "moneda": str(fila.get("moneda") or "USD").strip().upper()[:5] or "USD",
            "tipo_producto": tipo_prod,
            "costo_promedio": costo,
            "costo_reposicion_usd": costo_rep,
            "precio_venta_sugerido": precio,
            "codigo_barras": str(fila.get("codigo_barras") or "").strip()[:100] or None,
        }

    if entidad == "stock":
        sku = str(fila.get("sku") or "").strip()
        almacen = str(fila.get("almacen") or "").strip()
        if not sku or not almacen:
            raise MigracionError("Stock requiere 'sku' y 'almacen'.")
        return {
            "sku": sku[:100],
            "almacen": almacen[:20],
            "cantidad_disponible": _a_decimal(fila.get("cantidad_disponible"), "cantidad_disponible"),
            "cantidad_minima": _a_decimal(fila.get("cantidad_minima"), "cantidad_minima", Decimal("0")),
            "cantidad_maxima": _a_decimal(fila.get("cantidad_maxima"), "cantidad_maxima", Decimal("0")),
        }

    if entidad == "cxc_cxp":
        tipo = str(fila.get("tipo") or "CXC").strip().upper()
        if tipo not in {"CXC", "CXP"}:
            raise MigracionError(f"Tipo de cartera inválido '{tipo}'; use CXC o CXP.")
        rif = _normalizar_rif(fila.get("rif"))
        if not rif:
            raise MigracionError("CxC/CxP requiere 'rif' para vincular cliente o proveedor.")
        monto = _a_decimal(fila.get("monto"), "monto")
        if monto < Decimal("0"):
            raise MigracionError("El monto de CxC/CxP no puede ser negativo.")
        fecha_emision = _a_fecha(fila.get("fecha_emision"), "fecha_emision")
        fecha_vencimiento = _a_fecha(fila.get("fecha_vencimiento"), "fecha_vencimiento", default=fecha_emision)
        referencia = str(fila.get("referencia_externa") or "").strip()[:100] or None
        return {
            "tipo": tipo,
            "rif": rif[:20],
            "razon_social": str(fila.get("razon_social") or "").strip()[:255],
            "referencia_externa": referencia,
            "monto": monto,
            "fecha_emision": fecha_emision.isoformat(),
            "fecha_vencimiento": fecha_vencimiento.isoformat(),
            "estado": str(fila.get("estado") or "PENDIENTE").strip().upper(),
            "descripcion": str(fila.get("descripcion") or "").strip() or None,
        }

    raise MigracionError(f"Entidad no soportada: '{entidad}'.")


def _aplicar_fila_normalizada(empresa: Any, entidad: str, norm: dict[str, Any]) -> str:
    if entidad == "plan_cuentas":
        cuenta, creada = PlanCuentas.objects.update_or_create(
            id_empresa=empresa,
            codigo_cuenta=norm["codigo_cuenta"],
            defaults={
                "nombre_cuenta": norm["nombre_cuenta"],
                "tipo_cuenta": norm["tipo_cuenta"],
                "naturaleza": norm["naturaleza"],
                "nivel": norm["nivel"],
                "activo": norm["activo"],
            },
        )
        _ = cuenta
        return "creado" if creada else "actualizado"

    if entidad == "contactos":
        rol = norm["rol"]
        estado_res = "actualizado"
        if rol in {"CLIENTE", "AMBOS"}:
            datos_cli = {
                "razon_social": norm["razon_social"],
                "nombre_comercial": norm["nombre_comercial"],
                "direccion": norm["direccion"],
                "telefono": norm["telefono"],
                "email": norm["email"],
                "tipo_cliente": norm["tipo_cliente"],
                "limite_credito": norm["limite_credito"],
                "dias_credito": norm["dias_credito"],
            }
            cli = Cliente.objects.filter(id_empresa=empresa, rif=norm["rif"]).first()
            if cli is not None:
                for k, v in datos_cli.items():
                    setattr(cli, k, v)
                cli.full_clean(exclude=["contacto"])
                cli.save()
            else:
                cli = Cliente(id_empresa=empresa, rif=norm["rif"], **datos_cli)
                cli.full_clean(exclude=["contacto"])
                cli.save()
                estado_res = "creado"

        if rol in {"PROVEEDOR", "AMBOS"}:
            datos_prov = {
                "razon_social": norm["razon_social"],
                "nombre_comercial": norm["nombre_comercial"],
                "direccion": norm["direccion"],
                "telefono": norm["telefono"],
                "email": norm["email"],
            }
            prov = Proveedor.objects.filter(id_empresa=empresa, rif=norm["rif"]).first()
            if prov is not None:
                for k, v in datos_prov.items():
                    setattr(prov, k, v)
                prov.full_clean(exclude=["contacto"])
                prov.save()
            else:
                prov = Proveedor(id_empresa=empresa, rif=norm["rif"], **datos_prov)
                prov.full_clean(exclude=["contacto"])
                prov.save()
                estado_res = "creado"
        return estado_res

    if entidad == "productos":
        moneda = (
            Moneda.objects.filter(codigo_iso=norm["moneda"])
            .filter(Q(empresa__isnull=True) | Q(empresa=empresa))
            .first()
        )
        if moneda is None:
            raise MigracionError(f"No existe una moneda con código ISO '{norm['moneda']}'.")
        cat = CategoriaProducto.objects.filter(id_empresa=empresa, nombre_categoria=norm["categoria"]).first()
        if cat is None:
            cat = CategoriaProducto.objects.create(
                id_empresa=empresa,
                nombre_categoria=norm["categoria"],
            )
        unidad = UnidadMedida.objects.filter(id_empresa=empresa, abreviatura=norm["unidad_medida"]).first()
        if unidad is None:
            unidad = UnidadMedida.objects.create(
                id_empresa=empresa,
                nombre=norm["unidad_medida"],
                abreviatura=norm["unidad_medida"],
                tipo="CANTIDAD",
            )
        datos_prod = {
            "nombre_producto": norm["nombre_producto"],
            "id_categoria": cat,
            "id_unidad_medida_base": unidad,
            "id_moneda_precio": moneda,
            "tipo_producto": norm["tipo_producto"],
            "costo_promedio": norm["costo_promedio"],
            "costo_reposicion_usd": norm["costo_reposicion_usd"],
            "precio_venta_sugerido": norm["precio_venta_sugerido"],
            "codigo_barras": norm["codigo_barras"],
        }
        prod = Producto.objects.filter(id_empresa=empresa, sku=norm["sku"]).first()
        if prod is not None:
            for k, v in datos_prod.items():
                setattr(prod, k, v)
            prod.full_clean()
            prod.save()
            return "actualizado"
        prod = Producto(id_empresa=empresa, sku=norm["sku"], **datos_prod)
        prod.full_clean()
        prod.save()
        return "creado"

    if entidad == "stock":
        prod = Producto.objects.filter(id_empresa=empresa, sku=norm["sku"]).first()
        if prod is None:
            raise MigracionError(f"No existe producto con SKU '{norm['sku']}' en la empresa.")
        almacen = Almacen.objects.filter(id_empresa=empresa, codigo_almacen=norm["almacen"]).first()
        if almacen is None:
            raise MigracionError(f"No existe almacén con código '{norm['almacen']}' en la empresa.")
        stock = StockActual.objects.filter(
            id_empresa=empresa, id_producto=prod, id_variante__isnull=True, id_almacen=almacen
        ).first()
        if stock is not None:
            stock.cantidad_disponible = norm["cantidad_disponible"]
            stock.cantidad_minima = norm["cantidad_minima"]
            stock.cantidad_maxima = norm["cantidad_maxima"]
            stock.save()
            return "actualizado"
        StockActual.objects.create(
            id_empresa=empresa,
            id_producto=prod,
            id_almacen=almacen,
            cantidad_disponible=norm["cantidad_disponible"],
            cantidad_minima=norm["cantidad_minima"],
            cantidad_maxima=norm["cantidad_maxima"],
        )
        return "creado"

    if entidad == "cxc_cxp":
        fecha_emis = date.fromisoformat(norm["fecha_emision"])
        fecha_venc = date.fromisoformat(norm["fecha_vencimiento"])
        ref = norm["referencia_externa"]
        if norm["tipo"] == "CXC":
            cliente = Cliente.objects.filter(id_empresa=empresa, rif=norm["rif"]).first()
            if cliente is None:
                raise MigracionError(f"No existe Cliente con RIF '{norm['rif']}' en la empresa.")
            estado_cxc = norm["estado"].lower()
            if estado_cxc not in {"pendiente", "pagada", "vencida", "parcial"}:
                estado_cxc = "pendiente"
            if ref:
                existing = CuentaPorCobrar.objects.filter(
                    empresa=empresa, cliente=cliente, referencia_externa=ref
                ).first()
                if existing is not None:
                    existing.monto = norm["monto"]
                    existing.fecha_emision = fecha_emis
                    existing.fecha_vencimiento = fecha_venc
                    existing.estado = estado_cxc
                    existing.descripcion = norm["descripcion"]
                    existing.save()
                    return "actualizado"
            CuentaPorCobrar.objects.create(
                empresa=empresa,
                cliente=cliente,
                referencia_externa=ref,
                monto=norm["monto"],
                fecha_emision=fecha_emis,
                fecha_vencimiento=fecha_venc,
                estado=estado_cxc,
                descripcion=norm["descripcion"],
            )
            return "creado"

        proveedor = Proveedor.objects.filter(id_empresa=empresa, rif=norm["rif"]).first()
        if proveedor is None:
            raise MigracionError(f"No existe Proveedor con RIF '{norm['rif']}' en la empresa.")
        estado_cxp = norm["estado"].upper()
        if estado_cxp not in {"PENDIENTE", "PAGADA", "ANULADA", "VENCIDA", "PARCIAL"}:
            estado_cxp = "PENDIENTE"
        if ref:
            existing_cxp = CuentaPorPagar.objects.filter(
                id_empresa=empresa, id_proveedor=proveedor, referencia_externa=ref
            ).first()
            if existing_cxp is not None:
                existing_cxp.monto_total = norm["monto"]
                existing_cxp.monto_pendiente = norm["monto"]
                existing_cxp.fecha_emision = fecha_emis
                existing_cxp.fecha_vencimiento = fecha_venc
                existing_cxp.estado = estado_cxp
                existing_cxp.observaciones = norm["descripcion"]
                existing_cxp.save()
                return "actualizado"
        CuentaPorPagar.objects.create(
            id_empresa=empresa,
            id_proveedor=proveedor,
            referencia_externa=ref,
            monto_total=norm["monto"],
            monto_pendiente=norm["monto"],
            fecha_emision=fecha_emis,
            fecha_vencimiento=fecha_venc,
            estado=estado_cxp,
            observaciones=norm["descripcion"],
        )
        return "creado"

    raise MigracionError(f"Entidad no soportada: '{entidad}'.")


def _validar_fuente_y_entidad(fuente: str, entidad: str, limite: int) -> tuple[str, str, int]:
    f_norm = str(fuente or "").strip().upper()
    e_norm = str(entidad or "").strip().lower()
    if f_norm not in FUENTES_SOPORTADAS:
        raise MigracionError(f"Fuente no soportada '{fuente}'. Use: {', '.join(FUENTES_SOPORTADAS)}.")
    if e_norm not in ENTIDADES_SOPORTADAS:
        raise MigracionError(f"Entidad no soportada '{entidad}'. Use: {', '.join(ENTIDADES_SOPORTADAS)}.")
    if limite < 1 or limite > _LIMITE_MAX:
        raise MigracionError(f"El límite debe estar entre 1 y {_LIMITE_MAX}.")
    return f_norm, e_norm, limite


def _extraer_filas_fuente(
    empresa: Any,
    *,
    fuente: str,
    entidad: str,
    contenido_csv: bytes | str | None = None,
    id_conector: str | uuid.UUID | None = None,
    odoo_guard: OdooReadOnlyGuard | None = None,
    limite: int = 500,
) -> list[dict[str, Any]]:
    if fuente == "ODOO":
        guard = odoo_guard
        if guard is None:
            if not id_conector:
                raise MigracionError("La fuente ODOO requiere 'id_conector' perteneciente a la empresa.")
            guard = construir_guard_desde_conector(empresa, id_conector)
        extractors = {
            "plan_cuentas": guard.extraer_plan_cuentas,
            "contactos": guard.extraer_contactos,
            "productos": guard.extraer_productos,
            "stock": guard.extraer_stock,
            "cxc_cxp": guard.extraer_cxc_cxp,
        }
        try:
            return extractors[entidad](limite)
        except OdooCallError as exc:
            raise MigracionError(f"Error leyendo '{entidad}' desde Odoo: {exc}") from exc

    if contenido_csv is None:
        raise MigracionError(f"La fuente '{fuente}' requiere 'contenido_csv'.")
    return _parsear_csv_filas(contenido_csv, entidad, limite)


@dataclass
class _ResultadoValidacion:
    validos_norm: list[tuple[int, dict[str, Any], dict[str, Any]]]
    errores: list[dict[str, Any]]
    total_detectados: int


def _validar_lote(entidad: str, filas: list[dict[str, Any]]) -> _ResultadoValidacion:
    validos: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    errores: list[dict[str, Any]] = []
    for idx, raw in enumerate(filas, start=1):
        linea = int(raw.get("_linea") or idx)
        original = {k: str(v) for k, v in raw.items() if k != "_linea" and v is not None}
        try:
            norm = _normalizar_fila(entidad, raw)
            validos.append((linea, norm, original))
        except MigracionError as exc:
            errores.append({"fila": linea, "mensaje": str(exc), "datos": original})
    return _ResultadoValidacion(validos_norm=validos, errores=errores, total_detectados=len(filas))


def listar_formatos_migracion() -> dict[str, Any]:
    """Retorna fuentes soportadas (Odoo read-only, Saint, Profit, Galac), entidades y alias de columnas."""
    return {
        "odoo_solo_lectura": True,
        "odoo_metodos_permitidos": sorted(ALLOWED_ODOO_METHODS),
        "fuentes": [{"codigo": code, **_SOURCE_HINTS[code]} for code in FUENTES_SOPORTADAS],
        "entidades": list(ENTIDADES_SOPORTADAS),
        "columnas_canonicas": {
            entidad: {canon: list(aliases) for canon, aliases in campos.items()}
            for entidad, campos in COLUMN_ALIASES.items()
        },
    }


def preview_migracion_1click(
    empresa: Any,
    *,
    fuente: str,
    entidad: str,
    contenido_csv: bytes | str | None = None,
    id_conector: str | uuid.UUID | None = None,
    odoo_guard: OdooReadOnlyGuard | None = None,
    limite: int = 500,
    muestra: int = 10,
) -> dict[str, Any]:
    """Previsualiza y normaliza datos desde Odoo/Saint/Profit/Galac SIN mutar la base de datos."""
    f_norm, e_norm, lim = _validar_fuente_y_entidad(fuente, entidad, limite)
    filas = _extraer_filas_fuente(
        empresa,
        fuente=f_norm,
        entidad=e_norm,
        contenido_csv=contenido_csv,
        id_conector=id_conector,
        odoo_guard=odoo_guard,
        limite=lim,
    )
    res = _validar_lote(e_norm, filas)
    muestra_serializable: list[dict[str, Any]] = []
    for _, norm, _ in res.validos_norm[: max(1, min(muestra, 50))]:
        muestra_serializable.append({k: (str(v) if isinstance(v, Decimal) else v) for k, v in norm.items()})

    return {
        "empresa_id": str(empresa.pk),
        "fuente": f_norm,
        "entidad": e_norm,
        "dry_run": True,
        "total_detectados": res.total_detectados,
        "validos": len(res.validos_norm),
        "invalidos": len(res.errores),
        "muestra_normalizada": muestra_serializable,
        "errores": res.errores[:50],
    }


@transaction.atomic
def ejecutar_migracion_1click(
    empresa: Any,
    usuario: Any,
    *,
    fuente: str,
    entidad: str,
    contenido_csv: bytes | str | None = None,
    id_conector: str | uuid.UUID | None = None,
    odoo_guard: OdooReadOnlyGuard | None = None,
    limite: int = 500,
) -> dict[str, Any]:
    """Ejecuta importación 1-click idempotente registrando ``ProcesoMigracion`` y ``DetalleErrorMigracion``."""
    f_norm, e_norm, lim = _validar_fuente_y_entidad(fuente, entidad, limite)
    filas = _extraer_filas_fuente(
        empresa,
        fuente=f_norm,
        entidad=e_norm,
        contenido_csv=contenido_csv,
        id_conector=id_conector,
        odoo_guard=odoo_guard,
        limite=lim,
    )
    res = _validar_lote(e_norm, filas)

    plantilla, _ = PlantillaMigracion.objects.get_or_create(
        nombre_plantilla=f"1Click {f_norm} - {e_norm}",
        defaults={
            "modulo_destino": "migracion_datos",
            "modelo_destino": e_norm,
            "formato_archivo": "ODOO_XMLRPC_RO" if f_norm == "ODOO" else "CSV",
            "estructura_json": {"fuente": f_norm, "entidad": e_norm, "columnas": list(COLUMN_ALIASES[e_norm].keys())},
            "activo": True,
        },
    )
    proceso = ProcesoMigracion.objects.create(
        id_empresa=empresa,
        id_plantilla_migracion=plantilla,
        id_usuario_ejecutor=usuario,
        estado_proceso="EN_PROCESO",
        total_registros_procesados=res.total_detectados,
        ruta_archivo_cargado=f"1click://{f_norm.lower()}/{e_norm}",
    )

    errores_detalle: list[DetalleErrorMigracion] = []
    for err in res.errores:
        errores_detalle.append(
            DetalleErrorMigracion(
                id_proceso_migracion=proceso,
                numero_fila_archivo=err["fila"],
                campo_error="normalizacion",
                mensaje_error=err["mensaje"],
                datos_originales_json=err["datos"],
            )
        )

    creados = 0
    actualizados = 0
    errores_ejecucion: list[dict[str, Any]] = list(res.errores)

    for linea, norm, original in res.validos_norm:
        try:
            with transaction.atomic():
                resultado = _aplicar_fila_normalizada(empresa, e_norm, norm)
            if resultado == "creado":
                creados += 1
            else:
                actualizados += 1
        except (MigracionError, DjangoValidationError) as exc:
            msg = str(exc)
            errores_ejecucion.append({"fila": linea, "mensaje": msg, "datos": original})
            errores_detalle.append(
                DetalleErrorMigracion(
                    id_proceso_migracion=proceso,
                    numero_fila_archivo=linea,
                    campo_error=e_norm,
                    mensaje_error=msg,
                    datos_originales_json=original,
                )
            )

    if errores_detalle:
        DetalleErrorMigracion.objects.bulk_create(errores_detalle)

    exitosos = creados + actualizados
    fallidos = len(errores_ejecucion)
    if fallidos == 0:
        estado_final = "COMPLETADO"
    elif exitosos > 0:
        estado_final = "COMPLETADO_CON_ERRORES"
    else:
        estado_final = "FALLIDO"

    proceso.estado_proceso = estado_final
    proceso.total_registros_exitosos = exitosos
    proceso.total_registros_fallidos = fallidos
    proceso.fecha_fin = timezone.now()
    proceso.save(
        update_fields=[
            "estado_proceso",
            "total_registros_exitosos",
            "total_registros_fallidos",
            "fecha_fin",
        ]
    )

    return {
        "id_proceso_migracion": str(proceso.pk),
        "empresa_id": str(empresa.pk),
        "fuente": f_norm,
        "entidad": e_norm,
        "estado_proceso": estado_final,
        "total_detectados": res.total_detectados,
        "total_exitosos": exitosos,
        "creados": creados,
        "actualizados": actualizados,
        "total_fallidos": fallidos,
        "errores": errores_ejecucion[:50],
    }
