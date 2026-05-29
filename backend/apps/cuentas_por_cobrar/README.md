# App `cuentas_por_cobrar`

Cuentas por cobrar (CxC): saldos de clientes derivados de las ventas a crédito y sus abonos. Provee aging (antigüedad de saldos) y estado de cuenta en PDF.

**Prefijo API:** `/api/cxc/`

> No confundir con la app [`cxc`](../cxc/README.md) (Cobranza Inteligente), montada en `/api/cobranza/`. Esta app es el ledger de saldos; `cxc` es la gestión proactiva de cobranza.

## Modelos

| Modelo | Descripción |
|---|---|
| `CuentaPorCobrar` | Saldo por cobrar de un cliente/documento. |
| `AbonoCxC` | Abono/pago aplicado a una cuenta por cobrar. |

## Endpoints

Recursos REST (CRUD vía router): `cuentas-por-cobrar/`, `abonos-cxc/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET cuentas-por-cobrar/aging/` | Reporte de antigüedad de saldos. |
| `GET cuentas-por-cobrar/estado-cuenta/{cliente_id}/pdf/` | Estado de cuenta del cliente en PDF. |
| `POST cuentas-por-cobrar/{id}/abonar/` | Registrar un abono. |
