---
name: omni-frontend-i18n-l10n
description: Use this skill when frontend work touches user-facing text, language, or country-specific behavior in Omni. Triggers include adding/changing visible strings, working with react-i18next (useTranslation, locales/es.json|en.json), or showing/hiding features by active localization (Venezuela legal/market layers, multi-currency, IGTF, SENIAT). Use it whenever you'd hardcode a country assumption (VES, "Bs", IGTF, RIF) or a literal string into a screen meant to be internationalizable. Do NOT use for backend localization logic.
---

# Skill: i18n y Localización (l10n) en el Frontend de Omni

## Cuándo usar esta skill

Cargá esta skill cuando:
- Agregás o cambiás **texto visible** en una pantalla internacionalizable.
- Mostrás/ocultás features según el **país/localización** de la empresa.
- Estás por **hardcodear** algo específico de Venezuela (VES, "Bs", IGTF, RIF,
  SENIAT, doble tasa) en el núcleo.

## Dos conceptos distintos

Del plan maestro §3.7:

- **i18n (internacionalización):** *idioma* y formato (texto, fechas, números).
  Infraestructura: `react-i18next`.
- **l10n (localización):** *comportamiento* específico de país, en **dos capas**:
  - **Capa legal:** impuestos, formato de factura, libros fiscales (SENIAT/IGTF
    para VE).
  - **Capa de mercado:** métodos de pago, doble tasa, pagos de terceros.

> **Principio:** el ERP es internacionalizable por diseño. **Venezuela es la
> primera localización, no la base.** Nada específico de un país se incrusta en
> el núcleo: vive en un paquete de localización activable por empresa.

## i18n: cómo trabajar el texto

Setup: `frontend/src/i18n/index.ts` (init), locales en
`frontend/src/i18n/locales/{es,en}.json`. Idioma por defecto `es`, fallback `es`,
persistido en `localStorage['lang']`.

```tsx
import { useTranslation } from 'react-i18next';

function MiComponente() {
  const { t } = useTranslation();
  return <Button>{t('comun.guardar')}</Button>;
}
```

Convenciones:
- **Claves namespaced** por dominio/pantalla (`ventas.pedido.titulo`,
  `comun.guardar`), no la frase como clave.
- **Agregá la clave a `es.json` Y `en.json`** (mantené ambos en paridad; una
  clave sin traducción en `en` cae al fallback `es`, lo que delata el faltante).
- **Interpolación** con variables: `t('saldo.total', { monto })`. `escapeValue`
  está en false (React ya escapa).
- No concatenes fragmentos traducidos (rompe el orden en otros idiomas); usá una
  sola clave con interpolación.

> Estado real: muchas pantallas internas están en español directo (es la default
> del producto). No es obligatorio traducir cada pantalla interna hoy, pero **el
> texto nuevo en flujos de cara al cliente/futuro multipaís debería pasar por
> `t()`**. No introduzcas texto en inglés en la UI en español.

## l10n: features por localización activa

El núcleo opera **agnóstico**; las capacidades de un país se **muestran/ocultan**
según las capas activas de la empresa:

- **Empresa venezolana →** multimoneda real, doble tasa (BCV + paralela), IGTF,
  Pago Móvil/Zelle/USDT, libros SENIAT, RIF.
- **Empresa NO venezolana →** una moneda, factura simple, métodos de pago
  estándar, **sin** IGTF, **sin** doble tasa, **sin** pagos de terceros.

En la UI:
- **No hardcodees** VES, "Bs", IGTF, RIF, "BCV" como si siempre existieran.
- Mostrá columnas/campos/menús de una capa **solo si esa capa está activa** para
  la empresa. Una columna "IGTF" o "Tasa BCV" no debe aparecer para una empresa
  sin la capa VE activa.
- La moneda, el símbolo y los impuestos vienen de la **data** (catálogo de
  monedas, configuración fiscal de la empresa), no de constantes en el front.
- Para montos, esto se conecta con `omni-money-ui` (mostrar moneda explícita,
  conversión con tasa del backend).

> ADR-007 ("localización de dos capas") está **por redactar** y hoy la lógica VE
> está semi-incrustada (se migrará vía strangler fig). Mientras tanto: **no
> agregues nuevo acoplamiento a Venezuela en el núcleo del frontend.** Si una
> feature es VE-específica, aislala y condicionala por la capa activa, no la
> riegues por componentes genéricos.

## Formato de fechas y números

- Fechas: formato local del usuario; preferí `Intl.DateTimeFormat`/utilidades
  sobre strings hardcodeados `DD/MM/YYYY`.
- Números/moneda: `Intl.NumberFormat`/`formatCurrency` (ver `omni-money-ui`), con
  la moneda y los decimales que provee la data.

## Errores comunes a evitar

### Error 1: String literal en JSX en flujo internacionalizable
**Mal:** `<Button>Guardar</Button>` en una pantalla que debe ser multipaís.
**Bien:** `<Button>{t('comun.guardar')}</Button>`.

### Error 2: Texto en inglés en la UI en español
Inconsistencia. La default es `es`; nada de "Save"/"Loading..." sueltos.

### Error 3: Hardcodear Venezuela en el núcleo
**Mal:** `const SIMBOLO = 'Bs'`, columna IGTF siempre visible, etiqueta "RIF" fija.
**Bien:** símbolo/impuestos/etiquetas desde data + capas activas.

### Error 4: Clave i18n sin agregar a ambos locales
Queda un faltante silencioso. Agregá a `es.json` y `en.json`.

### Error 5: Concatenar traducciones
**Mal:** `t('hay') + count + t('items')`. **Bien:** `t('hay_items', { count })`.

### Error 6: Asumir una sola moneda
Romper multimoneda. La moneda es por-operación/por-empresa (ver `omni-money-ui`).

## Checklist antes de cerrar

- [ ] Texto nuevo de flujos internacionalizables vía `t()`; sin inglés en UI es.
- [ ] Claves namespaced presentes en `es.json` y `en.json`.
- [ ] Cero hardcode de VES/"Bs"/IGTF/RIF/BCV en componentes del núcleo.
- [ ] Features de capa VE condicionadas a la capa activa de la empresa.
- [ ] Moneda/impuestos/símbolos tomados de la data, no de constantes.
- [ ] Fechas/números con formato localizado.
- [ ] `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- `i18n/index.ts`, `i18n/locales/{es,en}.json`, `services/tasaBCV.ts`,
  `pages/Fiscal/*`, `utils/formatCurrency.ts`.
- Skills: `omni-money-ui`, `omni-venezuela-fiscal`, `omni-design-system`.
- Plan maestro §3.7 (l10n dos capas), ADR-007 (por redactar).
- Memoria: [[project_localizacion_l10n]].

## Changelog

### v1.0 — 2026-06-03
- Versión inicial.
