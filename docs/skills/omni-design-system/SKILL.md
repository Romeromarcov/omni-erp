---
name: omni-design-system
description: Use this skill whenever you touch the visual layer of the Omni frontend — colors, typography, spacing, shadows, theme, or shared UI components. Triggers include any task under `frontend/src/` that renders UI ("crea la página X", "agrega un botón/tarjeta/tabla", "ajusta el estilo de Y", "reskin de Z"), questions about the MUI theme, when to use `components/ui/`, or how to keep visual consistency across the ~100 pages. Apply it BEFORE writing any JSX with styling. Do NOT use for pure backend, pure data-fetching logic without UI, or build/test config.
---

# Skill: Sistema de Diseño de Omni (MUI v7)

## Cuándo usar esta skill

Cargá esta skill siempre que vayas a **renderizar o estilar UI**:
- Crear una página, una tarjeta, una tabla, un formulario, un diálogo.
- Elegir colores, tipografía, espaciado, bordes o sombras.
- Decidir si usar un componente de `components/ui/` o uno crudo de MUI.
- Migrar una página vieja al estilo actual (ver también `omni-frontend-reskin`).

No la cargués para lógica pura sin UI, ni para configuración de build/tests.

## Regla de oro: MUI v7, sin librerías de UI paralelas

El plan maestro (§3, tabla de stack) es explícito:

> **UI | MUI v7 (única librería UI permitida, sin wrappers propios)**

Esto significa:
- **MUI v7 (`@mui/material`, `@mui/icons-material`) es la única librería de
  componentes.** No introducir Chakra, Ant, Tailwind UI, shadcn, Bootstrap, ni
  ningún sistema de componentes alternativo.
- **"Sin wrappers propios"** = no construyas una librería de componentes que
  reemplace MUI ni que esconda su API. `components/ui/` SÍ está permitido y es el
  patrón canónico: son **convenience components muy delgados** que componen MUI
  para repetir menos (un `PageHeader`, una `DataTable`), no una capa de
  abstracción que reemplace `<Button>`/`<TextField>`. Si tu "wrapper" reescribe
  props de MUI o te impide pasar `sx`, vas por mal camino.
- **Estética = vía theme, no inline.** El look se centraliza en el `theme` de MUI
  (en `frontend/src/App.tsx`). No repartas `boxShadow`, `borderRadius`, colores
  hex sueltos por las páginas.

## El theme central

El theme vive **inline en `frontend/src/App.tsx`** (`createTheme({...})`) y se
inyecta con `<ThemeProvider>` + `<CssBaseline>`. Estado actual canónico:

```ts
palette: {
  primary:   { main: '#1976d2' },
  secondary: { main: '#dc004e' },
  background:{ default: '#f4f6f8' },
},
typography: {
  fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
  h5: { fontWeight: 700 }, h6: { fontWeight: 600 }, subtitle1: { fontWeight: 600 },
},
shape: { borderRadius: 8 },
components: {
  MuiButton:    contained sin elevación, textTransform 'none', fontWeight 600, radius 8
  MuiCard:      boxShadow suave '0 1px 4px rgba(0,0,0,0.08)', radius 12
  MuiPaper:     radius 12
  MuiTableHead: celdas en negrita, fondo '#f4f6f8'
  MuiChip:      fontWeight 600
}
```

> Nota: una memoria previa describía un "sistema futurista" con `theme/theme.ts`,
> `omni-tokens.css` y componentes `KpiCard`/`AppTile`/`AgingBars`. **Eso no está
> presente en esta rama.** Trabajá contra el theme real que ves en `App.tsx`. Si
> vas a evolucionar el theme, hacelo en ese archivo (o propone extraerlo a
> `theme/` en un PR de refactor dedicado, no mezclado con una feature).

### Cómo consumir el theme

- **Color:** usá tokens semánticos, nunca hex literales en las páginas.
  - `color="primary"`, `color="text.secondary"`, `bgcolor="background.paper"`,
    `borderColor: 'divider'`, `color="error"`.
  - En `sx`: `sx={{ color: 'text.secondary', bgcolor: 'grey.50' }}`.
- **Espaciado:** usá la escala de MUI (`p`, `m`, `gap`, `spacing`), no píxeles
  sueltos. `spacing(1) = 8px`. Ej: `<Stack spacing={2}>`, `sx={{ p: { xs: 2, md: 3 } }}`.
- **Bordes/sombras:** ya vienen del theme (Card/Paper). No re-agregues
  `borderRadius`/`boxShadow` manuales salvo necesidad real y justificada.
- **Tipografía:** usá `<Typography variant="h5|h6|subtitle1|body2|caption">`, no
  `<h2 style={{...}}>` ni font-sizes crudos.

## La librería `components/ui/`

Barrel: `frontend/src/components/ui/index.ts`. Componentes canónicos:

| Componente      | Para qué                                                        |
|-----------------|----------------------------------------------------------------|
| `PageContainer` | Wrapper de página a ancho completo dentro del shell (padding responsive, `maxWidth` 1280 por defecto, centrado). Para listados/dashboards. |
| `PageHeader`    | Cabecera: `title` + `subtitle?` + `actions?` (a la derecha). Responsive. |
| `DataTable<T>`  | Tabla tipada con `columns`, `rows`, `getRowKey`, estados `loading`/empty integrados y `onRowClick`. |
| `StatusChip`    | Chip de estado con mapa color por valor (activo/pendiente/anulado/pagado/vencido…). Acepta `colorMap` para override. |

`PageLayout` (en `components/PageLayout.tsx`, **fuera** de `ui/`) es el contenedor
tipo "tarjeta centrada" para **formularios y detalles** (Paper con `maxWidth`).
Convive con `PageContainer`: usá `PageContainer` para listados a ancho completo y
`PageLayout` para formularios/detalle angostos. (Históricamente muchas páginas
viejas envolvían TODO en `PageLayout`; al reskinear, mové los listados a
`PageContainer` + `PageHeader` + `DataTable`.)

### Plantilla mínima de página (listado)

```tsx
import { PageContainer, PageHeader, DataTable, StatusChip, type Column } from '../../components/ui';
import { Button, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/AddOutlined';

const columns: Column<Cliente>[] = [
  { key: 'nombre', header: 'Nombre', render: (r) => r.razon_social },
  { key: 'rif',    header: 'RIF',    render: (r) => r.rif },
  { key: 'estado', header: 'Estado', align: 'center', render: (r) => <StatusChip value={r.activo} /> },
];

export default function ClientesListPage() {
  // ...query con TanStack (ver skill omni-frontend-data)
  return (
    <PageContainer>
      <PageHeader
        title="Clientes"
        subtitle="Cartera de la empresa activa"
        actions={<Button variant="contained" startIcon={<AddIcon />} component={Link} to="new">Nuevo</Button>}
      />
      <DataTable columns={columns} rows={clientes} getRowKey={(r) => r.id_cliente} loading={isLoading} />
    </PageContainer>
  );
}
```

## Estados de UI obligatorios

Toda vista que cargue datos debe contemplar los tres estados — `DataTable` ya los
trae para listados, pero en vistas custom hacelo a mano:

- **Loading:** `<CircularProgress />` centrado (no texto "Cargando..." suelto).
- **Empty:** mensaje neutro en `text.secondary` (ej. "No se encontraron registros.").
- **Error:** `<Alert severity="error">` con mensaje legible (no `JSON.stringify`
  crudo del error al usuario).

## Iconografía

- Usá **`@mui/icons-material`**, variante **`Outlined`** (consistente con la
  navegación: `SpaceDashboardOutlined`, `PointOfSaleOutlined`, etc.).
- Importá el icono puntual (`import AddIcon from '@mui/icons-material/AddOutlined'`),
  no el barrel completo, para no inflar el bundle.

## Accesibilidad mínima (no negociable)

- Todo input tiene `label` (MUI `TextField label=...` ya asocia `<label>`).
- Botones de solo-icono llevan `aria-label` o un `<Tooltip>` con texto.
- Contraste: texto sobre fondo con ratio ≥ 4.5:1 (los tokens del theme cumplen;
  no inventes grises claros sobre blanco).
- Foco visible: no remuevas el outline de foco.
- Para auditorías profundas de a11y, apoyate en la skill de plugin
  `design:accessibility-review`.

## Errores comunes a evitar

### Error 1: Color hex hardcodeado
**Mal:** `<h2 style={{ color: '#1976d2' }}>`, `style={{ background: '#e3f0ff' }}`.
**Bien:** `<Typography variant="h5" color="primary">`, `sx={{ bgcolor: 'primary.light' }}`.
**Por qué:** un cambio de marca tendría que tocar 100 archivos. El theme es la fuente.

### Error 2: `<table>`/`<input>`/`<button>` HTML crudos con estilos inline
**Mal:** `<table style={{...}}>...<input style={{...}}>`.
**Bien:** `DataTable` / `TextField` / `Button` de MUI.
**Por qué:** rompe consistencia, accesibilidad y theming. Es el patrón legacy que
se está eliminando (ver `omni-frontend-reskin`).

### Error 3: Reintroducir `boxShadow`/`borderRadius` a mano
**Mal:** `<Card sx={{ boxShadow: '0 2px 8px ...', borderRadius: 12 }}>`.
**Bien:** `<Card>` a secas (el theme ya lo define).

### Error 4: Píxeles sueltos en vez de la escala de spacing
**Mal:** `sx={{ marginBottom: 24, padding: 12 }}`.
**Bien:** `sx={{ mb: 3, p: 1.5 }}`.

### Error 5: Introducir otra librería de UI o de estilos
**Mal:** agregar Tailwind, styled-components paralelo a emotion, Ant, etc.
**Bien:** MUI v7 + `sx`/`styled` de emotion (que ya trae MUI).
**Por qué:** R de stack: una sola librería de UI.

### Error 6: Inventar un wrapper que esconde MUI
**Mal:** `<MyButton>` que no acepta `sx`/`variant` y reescribe la API de MUI.
**Bien:** componer MUI en `components/ui/` dejando pasar las props relevantes.

## Checklist antes de cerrar

- [ ] Cero colores hex literales en JSX (todo vía tokens del theme).
- [ ] Cero `<table>/<input>/<button>` HTML crudos; uso de componentes MUI/ui.
- [ ] Listados con `PageContainer` + `PageHeader`; formularios/detalle con `PageLayout`.
- [ ] Estados loading / empty / error contemplados.
- [ ] Iconos `@mui/icons-material` variante Outlined, import puntual.
- [ ] Inputs con label; botones-icono con aria-label/tooltip.
- [ ] Sin `boxShadow`/`borderRadius`/spacing en px redundantes con el theme.
- [ ] `npx tsc -b` y `npm run lint` verdes.

## Referencias

- `frontend/src/App.tsx` (theme), `components/ui/` (barrel y componentes).
- Skills: `omni-frontend-page`, `omni-frontend-forms`, `omni-frontend-reskin`,
  `omni-frontend-responsive`.
- Plugin skills: `design:design-system`, `design:design-critique`,
  `design:accessibility-review`.
- Plan maestro `docs/PLAN_MAESTRO_UNICO.md` §3 (stack).

## Changelog

### v1.0 — 2026-06-03
- Versión inicial, alineada al theme y `components/ui/` reales de la rama.
