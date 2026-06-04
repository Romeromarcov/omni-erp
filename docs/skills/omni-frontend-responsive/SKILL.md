---
name: omni-frontend-responsive
description: Use this skill when making Omni frontend UI work across screen sizes and devices — mobile/tablet/desktop layout, responsive breakpoints, touch targets, the app shell (sidebar/drawer/topbar), bottom navigation, PWA, or the scanner module. Triggers include "que funcione en móvil", "hazlo responsive", "vista para tablet", adjusting AppLayout/Sidebar behavior, MUI breakpoints (xs/sm/md), or touch ergonomics. Do NOT use for backend or desktop-only visual tweaks unrelated to layout.
---

# Skill: Frontend Multiplataforma / Responsive en Omni

## Cuándo usar esta skill

Cargá esta skill cuando el trabajo afecte **cómo se ve y se usa la UI en
distintos dispositivos**: móvil, tablet, escritorio. Omni se diseña como
**frontend multiplataforma** — el dueño y los operadores de la distribuidora/
fábrica usan tanto desktop (back-office) como móvil (piso de venta, caja,
escáner). Una pantalla nueva debe ser usable en celular desde el día uno.

## El shell de la app ya es responsive

`components/layout/AppLayout.tsx` define el shell y su comportamiento por tamaño:
- **Desktop (`md+`):** `Sidebar` permanente (colapsable a "rail"; el estado
  `sidebar_collapsed` se persiste en localStorage). `Topbar` fijo + breadcrumbs.
- **Móvil (`<md`):** sidebar como `Drawer` temporal (se abre con el botón de
  menú, `keepMounted`). Contenido a ancho completo.
- Constantes en `components/layout/constants.ts` (`DRAWER_WIDTH`, `RAIL_WIDTH`,
  `TOPBAR_HEIGHT`). Reusalas, no inventes anchos.

`useMediaQuery(theme.breakpoints.down('md'))` es el patrón para ramear lógica por
tamaño. **No reimplementes el shell** dentro de una página.

## Breakpoints y diseño fluido (MUI)

Usá el sistema responsive de MUI, no media queries CSS sueltas:

```tsx
// padding/escala que crece con el viewport
<Box sx={{ p: { xs: 2, md: 3 } }} />

// columnas que se apilan en móvil
<Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} />

// grilla responsive
<Grid container spacing={2}>
  <Grid size={{ xs: 12, sm: 6, md: 4 }}>...</Grid>
</Grid>
```

Breakpoints MUI: `xs` (0), `sm` (600), `md` (900), `lg` (1200), `xl` (1536).
- `PageContainer` ya aplica padding responsive y centra con `maxWidth`.
- `PageHeader` ya apila título/acciones en `xs`.
- Mobile-first: pensá primero el `xs` y agregá overrides hacia arriba.

## Tablas en móvil

Las tablas densas son el punto débil en celular. Opciones (en orden de preferencia):
- `DataTable` dentro de un contenedor con scroll horizontal para datos tabulares
  ineludibles (el `TableContainer` ya permite overflow).
- Para pantallas de uso móvil intenso, considerá una **vista de tarjetas**
  (`Card` por registro) en `xs` y tabla en `md+` (ramear con `useMediaQuery`).
- Prioriza 2–3 columnas clave en móvil; el resto al detalle.

## Ergonomía táctil

- **Touch targets ≥ 44×44 px.** Botones de icono: tamaño `medium`/`large` en
  contextos móviles; evitá `size="small"` para acciones primarias en touch.
- Espaciá acciones para no provocar toques erróneos.
- Inputs con teclado adecuado: `type="number"`, `inputMode`, `type="date"`.
- Acciones primarias al alcance del pulgar (parte inferior) en flujos móviles.

## Navegación móvil y módulos táctiles

- El menú móvil vive en el `Drawer` temporal del `AppLayout` (fuente de verdad:
  `config/navigation.tsx`). Si se introduce una **bottom navigation** para los
  flujos más usados en móvil, debe consumir la misma `buildNavigation`, no un
  menú paralelo.
- **Módulo Escáner** (barcode/QR/NFC) es un caso de uso intrínsecamente móvil:
  targets grandes, feedback inmediato, manos-libres. Diseñá esas pantallas
  primero para `xs`.

## PWA / instalable

El proyecto incluye `vite-plugin-pwa`. Para experiencia tipo app:
- Respetá `safe-area` en dispositivos con notch cuando agregues barras fijas.
- Estados offline/carga deben ser claros (spinners, mensajes), no pantallas en
  blanco.
- No asumas hover: en touch no existe; toda interacción crítica debe funcionar
  con tap (no solo `:hover`).

## Accesibilidad que ayuda en móvil

- Texto legible sin zoom (no font-sizes < 14px para contenido).
- Contraste suficiente bajo sol/pantallas baratas (tokens del theme cumplen).
- Foco y orden de tabulación coherentes (también para teclados externos en tablet).

## Errores comunes a evitar

### Error 1: Anchos fijos en px
**Mal:** `sx={{ width: 1200 }}`. **Bien:** `maxWidth` + `width: '100%'` + breakpoints.

### Error 2: Tabla densa sin scroll ni alternativa en móvil
Se desborda o se vuelve ilegible. Scroll horizontal o vista de tarjetas en `xs`.

### Error 3: Media queries CSS crudas
**Mal:** `@media (max-width: 600px)` en un `.css`. **Bien:** `sx={{ xs:..., md:... }}` / `useMediaQuery`.

### Error 4: Targets táctiles diminutos
`IconButton size="small"` para la acción principal en móvil. Subí el tamaño.

### Error 5: Reimplementar el shell/menú
Otro sidebar/drawer. Reusá `AppLayout` + `buildNavigation`.

### Error 6: Depender de hover
Tooltips/acciones que solo aparecen al pasar el mouse. En touch no hay hover.

### Error 7: Anchos mágicos en vez de constantes del layout
Usá `DRAWER_WIDTH`/`RAIL_WIDTH`/`TOPBAR_HEIGHT`.

## Checklist antes de cerrar

- [ ] Probado mental/visualmente en `xs` (móvil), `md` (desktop).
- [ ] Layout con breakpoints MUI (`sx={{ xs, md }}`, `Stack direction`), sin px fijos.
- [ ] Tablas con scroll horizontal o vista alternativa en móvil.
- [ ] Touch targets ≥ 44px; inputs con teclado/tipo adecuado.
- [ ] Navegación reusa `AppLayout`/`buildNavigation` (sin menús paralelos).
- [ ] Nada crítico depende solo de hover.
- [ ] Constantes de layout reutilizadas.
- [ ] `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- `components/layout/AppLayout.tsx`, `Sidebar.tsx`, `Topbar.tsx`, `constants.ts`,
  `config/navigation.tsx`, `components/ui/PageContainer.tsx`, `vite.config.ts`
  (PWA).
- Skills: `omni-design-system`, `omni-frontend-page`, `omni-ai-native-ux`.
- Plan maestro (frontend multiplataforma; módulo escáner).
- Memoria: [[project_frontend_design_system]].

## Changelog

### v1.0 — 2026-06-03
- Versión inicial.
