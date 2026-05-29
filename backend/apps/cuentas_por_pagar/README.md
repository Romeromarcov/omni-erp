# App `cuentas_por_pagar`

Cuentas por pagar (CxP): saldos a proveedores derivados de las compras a crédito y sus abonos. Provee aging (antigüedad de saldos).

**Prefijo API:** `/api/cuentas-por-pagar/`

## Modelos

| Modelo | Descripción |
|---|---|
| `CuentaPorPagar` | Saldo por pagar a un proveedor/documento. |
| `AbonoCxP` | Abono/pago aplicado a una cuenta por pagar. |

## Endpoints

Recursos REST (CRUD vía router): `cuentas-por-pagar/`, `abonos-cxp/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET cuentas-por-pagar/aging/` | Reporte de antigüedad de saldos. |
| `POST cuentas-por-pagar/{id}/abonar/` | Registrar un abono. |
