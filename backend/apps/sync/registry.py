"""Registro de entidades sincronizables (réplica local de catálogo) — CTF-008
Nivel 2, primer incremento: pull de deltas (read-only).

Cada entrada declara el modelo, su clave primaria y la proyección EXPLÍCITA de
campos que se exponen al cliente offline. La proyección es una whitelist
(defensa en profundidad, igual criterio que CTF-005): nunca se serializa el
modelo completo, solo lo que el cliente necesita para operar sin red.

Todas las entidades de este primer incremento son catálogo de la empresa
(R-CODE-1): tienen `id_empresa`, `fecha_actualizacion` (delta) y `activo`
(para propagar bajas al cliente).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SyncEntity:
    #: Ruta "app.Model" para importación perezosa (evita imports circulares).
    model_label: str
    #: Nombre del campo PK (se expone como identificador estable del registro).
    pk_field: str
    #: Whitelist de campos a proyectar (incluye pk, fecha_actualizacion, activo).
    fields: tuple[str, ...]
    #: Campo FK a la empresa para el filtrado multi-tenant.
    empresa_field: str = "id_empresa"
    #: Campo timestamp usado como cursor de deltas.
    delta_field: str = "fecha_actualizacion"
    #: Búsquedas para `?desde` ordenadas de forma estable.
    order_by: tuple[str, ...] = field(default=("fecha_actualizacion", "pk"))


# Catálogo mínimo para operar un POS sin red. Ampliable sin tocar la vista.
SYNC_ENTITIES: dict[str, SyncEntity] = {
    "productos": SyncEntity(
        model_label="inventario.Producto",
        pk_field="id_producto",
        fields=(
            "id_producto", "nombre_producto", "sku", "id_categoria",
            "id_unidad_medida_base", "id_moneda_precio", "costo_promedio",
            "precio_venta_sugerido", "activo", "fecha_actualizacion",
        ),
    ),
    "categorias_producto": SyncEntity(
        model_label="inventario.CategoriaProducto",
        pk_field="id_categoria_producto",
        fields=(
            "id_categoria_producto", "nombre_categoria", "id_categoria_padre",
            "activo", "fecha_actualizacion",
        ),
    ),
    "unidades_medida": SyncEntity(
        model_label="inventario.UnidadMedida",
        pk_field="id_unidad_medida",
        fields=(
            "id_unidad_medida", "nombre", "abreviatura", "tipo",
            "activo", "fecha_actualizacion",
        ),
    ),
    "clientes": SyncEntity(
        model_label="crm.Cliente",
        pk_field="id_cliente",
        fields=(
            "id_cliente", "razon_social", "nombre_comercial", "rif",
            "telefono", "email", "tipo_cliente", "activo", "fecha_actualizacion",
        ),
    ),
}
