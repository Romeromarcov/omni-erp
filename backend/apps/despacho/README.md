# App `despacho`

Despacho/entrega de mercancía: documenta los despachos y sus líneas, enlazando ventas con la salida física de inventario.

**Prefijo API:** `/api/despacho/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Despacho` | Encabezado del despacho. |
| `DetalleDespacho` | Línea de despacho (producto/cantidad). |

## Endpoints

Recursos REST (CRUD vía router): `despachos/`, `detalles-despacho/`.
