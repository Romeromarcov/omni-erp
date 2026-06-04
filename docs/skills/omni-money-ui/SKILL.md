---
name: omni-money-ui
description: Use this skill whenever the frontend computes, formats, or displays money/amounts in the Omni ERP. Triggers include line subtotals, totals, taxes (IVA/IGTF), discounts, multi-currency display, exchange rates (BCV/paralela), payment amounts, or any arithmetic on monetary values in `frontend/src/`. Use it any time you'd otherwise write `+`, `*`, `parseFloat`, or `.toFixed` on a money value. Do NOT use for non-monetary numbers (counts, quantities without price) or backend money logic (see omni-decimal-money).
---

# Skill: Dinero en la UI del Frontend (decimal.js)

## Cuándo usar esta skill

Cargá esta skill siempre que toques **un valor monetario** en el frontend:
subtotales de línea, totales, descuentos, IVA/IGTF, vuelto, pagos, conversión
entre monedas, visualización de montos. Es la contraparte frontend de la regla
**R-CODE-4 (Decimal para dinero)** y de la skill backend `omni-decimal-money`.

## Por qué nunca float

JavaScript usa punto flotante binario: `0.1 + 0.2 === 0.30000000000000004`.
En un ERP eso significa facturas que no cuadran por centavos, IGTF mal calculado,
y saldos CxC que divergen del backend. **Prohibido** hacer aritmética de dinero
con los operadores nativos.

## Helpers canónicos: `lib/decimal.ts`

```ts
import { D, sumDecimals, subtotalLinea, toFixedStr } from '../lib/decimal';

D('1234.50')               // Decimal seguro (null/''/'abc' → 0, nunca NaN)
sumDecimals([a, b, c])     // suma con precisión decimal
subtotalLinea(cantidad, precio, descuentoPct)   // cantidad*precio - descuento%
toFixedStr(valor, 2)       // string con decimales fijos para enviar/mostrar
```

- **`D(x)`**: constructor seguro. Acepta `Decimal | string | number | null |
  undefined | ''`. Cualquier entrada inválida → `Decimal(0)` (no rompe la UI).
- **`sumDecimals(values)`**: reduce una lista a un `Decimal` sumado.
- **`subtotalLinea(cantidad, precio, descuentoPct?)`**: el cálculo estándar de
  una línea de documento (bruto = cantidad·precio; resta descuento %).
- **`toFixedStr(value, decimals=2)`**: formatea a string con decimales fijos.
  Úsalo para el **payload** que mandás al backend (string, no number).

### Ejemplo: total de un documento

```ts
import Decimal from 'decimal.js';
import { D, subtotalLinea, toFixedStr } from '../lib/decimal';

const subtotal = detalles.reduce<Decimal>(
  (acc, d) => acc.plus(subtotalLinea(d.cantidad, d.precio_unitario, d.descuento_porcentaje)),
  new Decimal(0),
);
const iva   = subtotal.times(D(tasaIva).dividedBy(100));
const total = subtotal.plus(iva);

// Mostrar / enviar:
const totalStr = toFixedStr(total, 2);    // "1234.50"
```

## Formateo para mostrar: `utils/formatCurrency.ts`

```ts
import { formatCurrency } from '../utils/formatCurrency';
formatCurrency(1234.5, 'USD')   // "$1,234.50"
formatCurrency('1234.5', 'VES') // localizado por moneda
```

Para mostrar al usuario, formateá con `formatCurrency` (o `Intl.NumberFormat`)
**al final**, después de calcular en Decimal. No mezcles cálculo y formato.

> Nota: `formatCurrency` hace `parseFloat` para mostrar — eso es aceptable para
> **presentación** (no se vuelve a operar sobre ese número). El cálculo siempre
> ocurre en Decimal antes.

## Multimoneda y doble tasa (Venezuela y más allá)

El ERP es **multimoneda real** (VES/USD/USDT simultáneas) con **doble tasa**:
oficial (BCV) + paralela/custom. Cada movimiento registra su equivalente en USD a
tasa oficial y a tasa real. En la UI:

- **Mostrá la moneda explícitamente** junto a cada monto (símbolo + código).
  Nunca muestres un número "pelado" sin moneda en pantallas de dinero.
- **No hardcodees VES ni "Bs"**: la moneda viene de la data (la empresa puede
  operar en otra). Esto se conecta con la l10n de dos capas — ver
  `omni-frontend-i18n-l10n`. Una empresa NO venezolana opera mono-moneda, sin
  IGTF, sin doble tasa: la UI debe ocultar esas columnas/campos según las capas
  activas.
- **Conversión:** usá la tasa que provee el backend/servicio (`services/tasaBCV`,
  `cxcKeys.tasasHoy()`), aplicada con Decimal. No inventes tasas en el cliente.
- **IGTF / IVA:** son cálculos fiscales sensibles; preferí que el monto fiscal lo
  calcule/confirme el backend (R-CODE-7 API-first). Si la UI previsualiza, usá
  Decimal y dejá claro que es estimado hasta confirmar.

## Inputs de monto en formularios

- En el schema zod, el monto es **`string`** validado (`Number(v) > 0`), no
  `number` (ver `omni-frontend-forms`).
- En el estado del form, guardá el string tal cual lo escribe el usuario.
- Al calcular o enviar, pasá por `D(...)` / `toFixedStr(...)`.

## Errores comunes a evitar

### Error 1: Aritmética nativa sobre dinero
**Mal:** `cantidad * precio`, `subtotal + iva`, `total.toFixed(2)` sobre un number.
**Bien:** `subtotalLinea(...)`, `D(a).plus(D(b))`, `toFixedStr(total)`.

### Error 2: `parseFloat`/`Number` para luego operar
**Mal:** `const t = parseFloat(a) + parseFloat(b)`.
**Bien:** `const t = D(a).plus(D(b))`. (`parseFloat` solo para presentación final.)

### Error 3: Enviar number al backend
**Mal:** `monto: Number(values.monto)`.
**Bien:** `monto: toFixedStr(values.monto, decimales)` (string).

### Error 4: Monto sin moneda en pantalla
**Mal:** "1.234,50". **Bien:** "USD 1.234,50" / "Bs 1.234,50" según la data.

### Error 5: Hardcodear VES / "Bs" / IGTF
**Mal:** asumir Venezuela. **Bien:** moneda y capas fiscales desde la data/l10n.

### Error 6: Recalcular impuestos fiscales solo en el cliente como verdad
**Mal:** confiar en el IVA/IGTF calculado en JS como definitivo.
**Bien:** previsualizar con Decimal; el valor fiscal lo confirma el backend.

## Checklist antes de cerrar

- [ ] Cero `+`/`-`/`*`/`/` nativos sobre montos; todo vía `lib/decimal`.
- [ ] `parseFloat`/`Number` solo en el formateo de presentación final.
- [ ] Montos enviados como string (`toFixedStr`), no number.
- [ ] Cada monto en pantalla muestra su moneda; sin VES/"Bs"/IGTF hardcodeado.
- [ ] Conversión con tasa provista por backend/servicio, aplicada en Decimal.
- [ ] Decimales respetan los de la moneda (`Moneda.decimales`).
- [ ] `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- `lib/decimal.ts`, `utils/formatCurrency.ts`, `services/tasaBCV.ts`,
  `lib/queryKeys.ts` (`cxcKeys.tasasHoy`), `__tests__/decimal.test.ts`.
- Skills: `omni-decimal-money` (backend), `omni-frontend-forms`,
  `omni-frontend-i18n-l10n`, `omni-venezuela-fiscal`.
- Plan maestro §3.7 (multimoneda, doble tasa), R-CODE-4.

## Changelog

### v1.0 — 2026-06-03
- Versión inicial.
