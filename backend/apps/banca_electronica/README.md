# apps/banca_electronica

Módulo de banca operativa venezolana (VE) y lotes de pago masivos sobre el maestro canónico `finanzas.CuentaBancariaEmpresa`.

## Modelos principales

- `LotePagoBancario`: Lote de pagos masivos a proveedores o nómina en formatos `BANESCO_TXT`, `MERCANTIL_TXT`, `BDV_TXT` y `GENERICO_CSV` con SHA-256 e inmutabilidad tras `ANULADO`/`PROCESADO`.
- `DetalleLotePagoBancario`: Línea individual por beneficiario vinculada opcionalmente a `finanzas.Pago` o `nomina.Nomina`.

## Servicios y validadores

- `validar_cuenta_bancaria_ve`: Valida 20 dígitos y prefijo SUDEBAN de bancos venezolanos.
- `validar_referencia_bancaria`: Detecta duplicados case-insensitive en `finanzas.Pago`, `tesoreria.MovimientoBancario` y `DetalleLotePagoBancario` activo dentro del tenant.
- `generar_lote_pagos_proveedores`, `generar_lote_pagos_nomina` y `cambiar_estado_lote`.

## API REST (`/api/banca-electronica/`)

- `/lotes-pago/` (`GET`, `generar-proveedores`, `generar-nomina`, `descargar`, `marcar-enviado`, `marcar-procesado`, `anular`).
- `/validar-referencia/` (`POST`).
- `/validar-cuenta-ve/` (`POST`).

Las cuentas bancarias empresariales se gestionan en el maestro canónico `/api/finanzas/cuentas-bancarias-empresa/`.
