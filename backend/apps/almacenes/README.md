# App `almacenes`

Maestro de almacenes y sus ubicaciones físicas internas. Da estructura espacial al stock gestionado por `inventario`.

**Prefijo API:** `/api/almacenes/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Almacen` | Almacén/depósito de una empresa o sucursal. |
| `UbicacionAlmacen` | Ubicación física dentro de un almacén (pasillo, estante, etc.). |

## Endpoints

Recursos REST (CRUD vía router): `almacenes/`, `ubicaciones-almacen/`.
