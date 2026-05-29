# App `proveedores`

Maestro de proveedores: proveedores, sus contactos y sus cuentas bancarias. Alimenta compras y cuentas por pagar.

**Prefijo API:** `/api/proveedores/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Proveedor` | Maestro de proveedor (RIF, datos fiscales). |
| `ContactoProveedor` | Contactos del proveedor. |
| `CuentaBancariaProveedor` | Cuentas bancarias para pagos al proveedor. |

## Endpoints

Recursos REST (CRUD vía router): `proveedores/`, `contactos-proveedor/`, `cuentas-bancarias-proveedor/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET proveedores/buscar-por-rif/` | Buscar proveedor por RIF. |
