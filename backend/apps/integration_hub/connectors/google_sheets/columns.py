"""
Definición de columnas por entidad para el conector Google Sheets.

Cada entidad canónica (la que entrega el conector de origen, p. ej. Odoo) se
proyecta a una hoja con columnas ordenadas y encabezados legibles. El orden es
estable para que el upsert por fila (clave ``id_externo``) sea consistente entre
ejecuciones.

Las claves de campo coinciden con la forma canónica del Hub (ver
``OdooConnector.normalizar_*``). Los campos internos (``_checksum``, ``_fuente``)
no se exportan; las listas/dicts anidados (p. ej. ``lineas``) se serializan a
JSON en una sola celda.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

# Columna clave para el upsert incremental (debe ser la primera de cada hoja).
COLUMNA_CLAVE = "id_externo"

# Título de la pestaña (worksheet) por entidad.
HOJAS = {
    "contactos": "Contactos",
    "productos": "Productos",
    "pedidos_venta": "Pedidos de Venta",
    "pedidos_compra": "Pedidos de Compra",
    "facturas_venta": "Facturas de Venta",
    "pagos": "Pagos",
    "inventario": "Inventario",
}

# (campo_canonico, encabezado_humano) — el orden define el orden de columnas.
COLUMNAS: dict[str, list[tuple[str, str]]] = {
    "contactos": [
        ("id_externo", "ID Externo"),
        ("nombre", "Nombre"),
        ("email", "Email"),
        ("telefono", "Teléfono"),
        ("movil", "Móvil"),
        ("es_cliente", "Cliente"),
        ("es_proveedor", "Proveedor"),
        ("es_empresa", "Es Empresa"),
        ("identificador_fiscal", "Identificador Fiscal"),
        ("direccion", "Dirección"),
        ("ciudad", "Ciudad"),
        ("estado_provincia", "Estado/Provincia"),
        ("pais_nombre", "País"),
        ("website", "Sitio Web"),
        ("notas", "Notas"),
        ("activo", "Activo"),
        ("fecha_modificacion_externo", "Última Modificación"),
    ],
    "productos": [
        ("id_externo", "ID Externo"),
        ("nombre", "Nombre"),
        ("codigo_interno", "Código"),
        ("descripcion_venta", "Descripción"),
        ("precio_venta", "Precio Venta"),
        ("costo", "Costo"),
        ("categoria_nombre", "Categoría"),
        ("unidad_medida", "Unidad"),
        ("tipo", "Tipo"),
        ("codigo_barras", "Código de Barras"),
        ("disponible_venta", "Vendible"),
        ("disponible_compra", "Comprable"),
        ("activo", "Activo"),
        ("fecha_modificacion_externo", "Última Modificación"),
    ],
    "pedidos_venta": [
        ("id_externo", "ID Externo"),
        ("numero", "Número"),
        ("cliente_nombre", "Cliente"),
        ("vendedor_nombre", "Vendedor"),
        ("fecha_pedido", "Fecha"),
        ("estado", "Estado"),
        ("estado_factura", "Estado Factura"),
        ("subtotal", "Subtotal"),
        ("impuestos", "Impuestos"),
        ("total", "Total"),
        ("moneda", "Moneda"),
        ("termino_pago", "Término de Pago"),
        ("lineas", "Líneas (JSON)"),
        ("fecha_modificacion_externo", "Última Modificación"),
    ],
    "pedidos_compra": [
        ("id_externo", "ID Externo"),
        ("numero", "Número"),
        ("proveedor_nombre", "Proveedor"),
        ("fecha_pedido", "Fecha"),
        ("fecha_aprobacion", "Fecha Aprobación"),
        ("estado", "Estado"),
        ("estado_factura", "Estado Factura"),
        ("subtotal", "Subtotal"),
        ("impuestos", "Impuestos"),
        ("total", "Total"),
        ("moneda", "Moneda"),
        ("lineas", "Líneas (JSON)"),
        ("fecha_modificacion_externo", "Última Modificación"),
    ],
    "facturas_venta": [
        ("id_externo", "ID Externo"),
        ("numero", "Número"),
        ("referencia", "Referencia"),
        ("origen_pedido", "Origen"),
        ("cliente_nombre", "Cliente"),
        ("fecha_factura", "Fecha Factura"),
        ("fecha_vencimiento", "Vencimiento"),
        ("subtotal", "Subtotal"),
        ("impuestos", "Impuestos"),
        ("total", "Total"),
        ("saldo_pendiente", "Saldo Pendiente"),
        ("moneda", "Moneda"),
        ("estado_pago", "Estado de Pago"),
        ("fecha_modificacion_externo", "Última Modificación"),
    ],
    "pagos": [
        ("id_externo", "ID Externo"),
        ("numero", "Número"),
        ("tipo", "Tipo"),
        ("tipo_socio", "Tipo Socio"),
        ("socio_nombre", "Socio"),
        ("monto", "Monto"),
        ("fecha", "Fecha"),
        ("estado", "Estado"),
        ("diario", "Diario"),
        ("moneda", "Moneda"),
        ("referencia", "Referencia"),
        ("fecha_modificacion_externo", "Última Modificación"),
    ],
    "inventario": [
        ("id_externo", "ID Externo"),
        ("producto_nombre", "Producto"),
        ("ubicacion_nombre", "Ubicación"),
        ("cantidad", "Cantidad"),
        ("cantidad_reservada", "Reservada"),
        ("cantidad_disponible", "Disponible"),
        ("lote", "Lote"),
    ],
}


def entidades_soportadas() -> list[str]:
    """Lista de tipos de entidad que el conector Sheets sabe exportar."""
    return list(COLUMNAS.keys())


def hoja_de(tipo_entidad: str) -> str:
    """Nombre de la pestaña (worksheet) para una entidad."""
    return HOJAS.get(tipo_entidad, tipo_entidad)


# Caracteres con los que una celda de texto sería interpretada como fórmula por
# Sheets (value_input_option="USER_ENTERED"). Se neutralizan anteponiendo "'"
# (CWE-1236, inyección de fórmulas). NO aplica a numéricos: los montos llegan
# como Decimal y los negativos legítimos (-5.00) no deben alterarse.
_PREFIJOS_FORMULA = ("=", "+", "-", "@")


def _proteger_formula(texto: str) -> str:
    if texto and texto[0] in _PREFIJOS_FORMULA:
        return "'" + texto
    return texto


def _cell(value: Any) -> Any:
    """Proyecta un valor canónico a una celda de Sheets (texto o numérico)."""
    # bool va primero: True/False no deben caer en la rama de "vacío".
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if value is None or value == "":
        return ""
    if isinstance(value, Decimal):
        # str preserva la precisión exacta; USER_ENTERED lo interpreta como número.
        return str(value)
    if isinstance(value, (list, tuple, dict)):
        return _proteger_formula(json.dumps(value, ensure_ascii=False, default=str))
    if isinstance(value, str):
        return _proteger_formula(value)
    return value


def build_rows(
    tipo_entidad: str, registros: list[dict]
) -> tuple[list[str], list[list]]:
    """
    Construye ``(encabezado, filas)`` para una entidad.

    El llamador debe validar ``tipo_entidad`` con ``entidades_soportadas()``
    antes de invocar (de lo contrario lanza ``KeyError``).
    """
    columnas = COLUMNAS[tipo_entidad]
    header = [titulo for _, titulo in columnas]
    rows = [[_cell(rec.get(campo)) for campo, _ in columnas] for rec in registros]
    return header, rows


def indice_clave(tipo_entidad: str) -> int:
    """Posición (0-based) de la columna clave ``id_externo`` en la entidad."""
    for i, (campo, _) in enumerate(COLUMNAS[tipo_entidad]):
        if campo == COLUMNA_CLAVE:
            return i
    return 0
