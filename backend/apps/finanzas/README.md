# App `finanzas`

Núcleo financiero y de tesorería operativa. Es una de las apps más grandes del sistema. Cubre multimoneda y tasas de cambio, métodos de pago, cajas (físicas y virtuales, con plantillas y autogeneración), datáfonos (puntos de venta de tarjeta), transacciones financieras y el registro de pagos. Soporta la realidad monetaria venezolana: multimoneda real y pagos mixtos.

**Prefijo API:** `/api/finanzas/`

## Modelos (por área)

**Moneda y tasas:** `Moneda`, `TasaCambio`, `MonedaEmpresaActiva`, `MetodoPago`, `MetodoPagoEmpresaActiva`.

**Cajas:** `Caja`, `CajaFisica`, `CajaUsuario`, `CajaFisicaUsuario`, `CajaVirtualUsuario`, `SesionCajaFisica`, `PlantillaMaestroCajasVirtuales`, `CajaVirtualAuto`, `CajaMetodoPagoOverride`.

**Bancos y movimientos:** `CuentaBancariaEmpresa`, `MovimientoCajaBanco`, `TransaccionFinanciera`, `Pago`.

**Datáfonos:** `Datafono`, `SesionDatafono`, `TransaccionDatafono`, `DepositoDatafono`.

## Endpoints

### Recursos REST (CRUD vía router)

`monedas/`, `tasas-cambio/`, `metodos-pago/`, `monedas-empresa-activas/`, `transacciones-financieras/`, `movimientos-caja-banco/`, `ajustes-caja-banco/`, `cajas/`, `cajas-fisicas/`, `cajas-usuario/`, `cajas-fisicas-usuario/`, `plantillas-maestro-cajas/`, `cajas-virtuales-auto/`, `overrides-metodos-pago/`, `sesiones-caja/`, `cuentas-bancarias-empresa/` (y alias `cuentas-bancarias/`), `datafono/` / `datafonos/`, `transacciones-datafono/`, `sesiones-datafono/`, `depositos-datafono/`, `pagos/`.

### Rutas y acciones destacadas

| Ruta | Descripción |
|---|---|
| `GET tasa-oficial-bcv/` | Tasa de cambio oficial del BCV. |
| `POST cajas/{id}/cerrar/` · `cierre/` | Cerrar caja / cierre de caja. |
| `POST cajas/{id}/transferir-entre-cajas/` | Transferencia entre cajas. |
| `POST cajas/{id}/crear-caja-virtual/` | Crear caja virtual. |
| `GET cajas/{id}/movimientos-caja-banco/` · `movimientos-cuenta-bancaria/` | Movimientos asociados. |
| `GET cajas-usuario/activas/` · `buscar_reutilizar/` · `POST {id}/reutilizar/` | Gestión de cajas virtuales de usuario. |
| `POST datafono/{id}/cierre/` · `cerrar-sesion/` · `registrar-pago/` | Operaciones de datáfono. |
| `POST depositos-datafono/{id}/conciliar/` · `GET pendientes/` | Conciliación de depósitos. |
| `GET .../tipos-documento/` · `tipos-operacion/` · `tipo-caja-choices/` | Catálogos auxiliares. |
