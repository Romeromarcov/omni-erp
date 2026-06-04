---
name: omni-frontend-reskin
description: Use this skill when migrating a legacy Omni frontend page to the current design system — converting inline-styled HTML tables/inputs and hardcoded colors into MUI + components/ui, or moving a useState form to react-hook-form + zod. Triggers include "reskin de la página X", "moderniza la vista Y", "migra Z al nuevo diseño", "quita los estilos inline", or any work on branch `frontend-forms-reskin`. Do NOT use for brand-new pages (use omni-frontend-page) — this is specifically for converting existing legacy screens.
---

# Skill: Reskin / Migración de Páginas Legacy

## Cuándo usar esta skill

El frontend está **a mitad de una migración**: conviven páginas legacy (estilos
inline, `<table>`/`<input>` HTML crudos, colores hex hardcodeados, formularios con
`useState` manual) con el patrón actual (MUI + `components/ui` + react-hook-form +
zod + TanStack Query). La rama `frontend-forms-reskin` es exactamente este trabajo.

Cargá esta skill cuando vas a **convertir una pantalla existente** al estándar.
Para páginas nuevas usá `omni-frontend-page`; esta skill es para migrar.

## Cómo reconocer una página legacy (señales)

- Importa `PageLayout` y mete TODO (incluido un listado) dentro.
- `<h2 style={{ color: '#1976d2' }}>`, `<table style={{...}}>`, `<input style>`,
  `<Link style={{ background: '#1976d2' }}>`.
- Colores hex literales (`#1976d2`, `#e3f0ff`, `#d32f2f`, `#888`) repartidos.
- Estado de formulario con muchos `useState` + validación a mano en `onSubmit`.
- `alert()` / `window.confirm()` / `console.log`.
- `fetch` directo o `.then()` sueltos en vez de TanStack Query.
- Lectura de `.results` a mano en vez de `toList`.

Ejemplo real legacy: `pages/Finanzas/Monedas/MonedaListPage.tsx` (tabla y inputs
inline con hex) — buen candidato de práctica.

## Receta de migración (listado)

1. **Wrapper:** `PageLayout` (envolviendo un listado) → `PageContainer` +
   `PageHeader title=... subtitle=... actions=...`.
2. **Encabezado:** `<h2 style>` → el `title` del `PageHeader`. El botón "Nuevo"
   (`<Link style={{background}}>`) → `<Button variant="contained" startIcon component={Link}>`.
3. **Búsqueda:** `<input style>` → `<TextField size="small" placeholder>`.
4. **Tabla:** `<table>/<thead>/<tbody>` inline → `DataTable` con `Column<T>[]`,
   `rows`, `getRowKey`, `loading`, `onRowClick`.
5. **Estados:** "Cargando..." / "Error" en divs con hex → `loading` del DataTable
   + `<Alert severity="error">` para error.
6. **Estado (activo/pendiente/…):** texto plano o "Sí/No" → `<StatusChip value>`.
7. **Datos:** `useQuery` + key de `lib/queryKeys` + `select: toList` (si no estaba).
8. **Colores:** eliminá todo hex; usá tokens del theme (`color="primary"`,
   `text.secondary`, etc.).

## Receta de migración (formulario)

1. Define/usa el **schema zod** en `schemas/<dominio>.schemas.ts` con `z.infer`.
2. Reemplazá los `useState` por `useForm({ resolver: zodResolver, mode: 'onBlur', defaultValues })`.
3. Inputs → `TextField` con `register` (texto/número) o `Controller` (select,
   checkbox, date, custom). Errores → `error`/`helperText`.
4. `alert`/`confirm` → `useSnackbar()` / `useConfirm()`.
5. Submit → `useMutation` (post/patch) con invalidación + navegación + snackbar.
6. Montos → string en el schema + `lib/decimal` para cálculos (ver `omni-money-ui`).
7. `disabled={saving}` durante el envío.

Ver el detalle en `omni-frontend-forms`; el resultado debe verse como
`MonedaFormPage.tsx` (que ya está migrado a rhf+zod).

## Disciplina de la migración

- **Equivalencia de comportamiento primero.** El reskin **no cambia la lógica de
  negocio**: mismos campos, mismas validaciones efectivas, mismos endpoints,
  mismos resultados. Si encontrás un bug de lógica, es **otro PR** (no mezcles
  refactor visual con fix de comportamiento — anti-patrón de `omni-pr-discipline`).
- **Una página (o un grupo cohesivo) por PR.** No reskinees 15 páginas en un PR
  gigante. Mantené el diff focal (R-PROC-2).
- **Tests:** si la página tiene test, debe seguir verde tras el reskin; ajustá
  selectores si cambiaron roles/labels (MUI expone roles accesibles — testeá por
  rol/label, no por estilos). Si no tenía test y el flujo es relevante, considerá
  agregar uno.
- **Sin regresiones de a11y/responsive:** la versión nueva debe ser igual o más
  accesible y usable en móvil (ver `omni-design-system`, `omni-frontend-responsive`).
- **Borrá el código muerto** (estilos inline, helpers locales `toList` duplicados,
  imports sin usar) que deja la migración.

## Antes / Después (mini)

```tsx
// ANTES (legacy)
<h2 style={{ textAlign: 'center', color: '#1976d2' }}>Monedas</h2>
<input style={{ border: '1px solid #cfd8dc' }} value={search} onChange={...} />
<table style={{ background: '#f6fafd' }}>...</table>

// DESPUÉS (estándar)
<PageContainer>
  <PageHeader title="Monedas" subtitle="Catálogo de monedas"
    actions={<Button variant="contained" startIcon={<AddIcon />} component={Link} to="new">Nueva</Button>} />
  <TextField size="small" placeholder="Buscar…" value={search} onChange={...} sx={{ mb: 2 }} />
  <DataTable columns={columns} rows={filtered} getRowKey={(r) => r.id_moneda} loading={isLoading} />
</PageContainer>
```

## Errores comunes a evitar

### Error 1: Mezclar reskin con cambio de lógica
**Mal:** "de paso arreglé el cálculo y agregué un campo". **Bien:** reskin puro;
lógica en otro PR.

### Error 2: Dejar hex/inline "porque andaba"
El objetivo del reskin es justamente eliminarlos. Cero hex/inline al terminar.

### Error 3: PR gigante de N páginas
Difícil de revisar, fácil de romper. Una página/grupo por PR.

### Error 4: Romper tests por selectores frágiles
Testeá por rol/label accesible, no por clases/estilos.

### Error 5: Perder un estado (empty/error) que el legacy sí tenía
Verificá paridad de estados loading/empty/error.

### Error 6: Olvidar mover el listado de `PageLayout` a `PageContainer`
`PageLayout` es para forms/detalle (tarjeta angosta); listados van en `PageContainer`.

## Checklist antes de cerrar

- [ ] Cero estilos inline / colores hex; todo MUI + tokens del theme.
- [ ] Listado en `PageContainer`+`PageHeader`+`DataTable`; form en rhf+zod.
- [ ] `StatusChip` para estados; `Alert`/loading para error/carga.
- [ ] Datos vía TanStack Query + `queryKeys` + `toList`.
- [ ] `alert`/`confirm`/`console.log` eliminados (snackbar/confirm).
- [ ] Comportamiento equivalente al legacy (sin cambios de lógica colados).
- [ ] Tests existentes verdes; código muerto borrado.
- [ ] PR focal (una página/grupo). `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- Legacy de práctica: `pages/Finanzas/Monedas/MonedaListPage.tsx`.
- Ya migrado: `pages/Finanzas/Monedas/MonedaFormPage.tsx`.
- Skills: `omni-design-system`, `omni-frontend-page`, `omni-frontend-forms`,
  `omni-frontend-data`, `omni-frontend-responsive`, `omni-pr-discipline`.

## Changelog

### v1.0 — 2026-06-03
- Versión inicial (rama frontend-forms-reskin).
