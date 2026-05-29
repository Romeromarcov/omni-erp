# App `crm`

Gestión de clientes: el maestro de clientes, sus contactos y direcciones. Punto de entrada de la relación comercial; alimenta ventas, CxC y cobranza.

**Prefijo API:** `/api/crm/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Cliente` | Maestro de cliente (RIF/cédula, crédito, datos fiscales). |
| `ContactoCliente` | Contactos del cliente. |
| `DireccionCliente` | Direcciones (facturación/entrega). |

## Endpoints

Recursos REST (CRUD vía router): `clientes/`, `contactos-cliente/`, `direcciones-cliente/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET clientes/buscar-por-rif/` | Buscar cliente por RIF. |
| `GET clientes/{id}/historial-ventas/` | Historial de ventas del cliente. |
| `GET clientes/{id}/credito-disponible/` | Crédito disponible del cliente. |
