---
name: omni-frontend-page
description: Use this skill whenever you create or restructure a frontend page/screen in the Omni ERP. Triggers include any task that adds a route under `frontend/src/pages/`, requests like "crea la página de listado/detalle/formulario para X", "agrega la vista de Y al módulo Z", wiring a new screen into the router/sidebar, or building list+detail+form trios for a business entity. Do NOT use for backend, for purely visual tweaks to an existing page (use omni-design-system), or for form-internal validation logic alone (use omni-frontend-forms).
---

# Skill: Crear una Página del Frontend de Omni

## Cuándo usar esta skill

Cargá esta skill cuando vas a:
- Crear una vista nueva (listado, detalle, formulario) para una entidad.
- Conectar una página al router y a la navegación lateral.
- Estandarizar una página existente a la anatomía canónica.

Trabaja junto con: `omni-design-system` (estética), `omni-frontend-data`
(fetching), `omni-frontend-forms` (formularios), `omni-money-ui` (montos).

## Estructura de archivos

Las páginas viven bajo `frontend/src/pages/<Modulo>/<Entidad>/`:

```
frontend/src/pages/Finanzas/Monedas/
├── MonedaListPage.tsx      # Listado (tabla + búsqueda + acción "Nuevo")
├── MonedaDetailPage.tsx    # Detalle (ver / editar)
└── MonedaFormPage.tsx      # Alta (y a veces edición)
```

Convenciones de nombre:
- Componentes y archivos en **PascalCase** terminados en `Page`:
  `XListPage`, `XDetailPage`, `XFormPage`, `XCreatePage`.
- Carpeta de módulo en PascalCase español (`Ventas`, `Finanzas`, `Inventario`,
  `Configuracion`, `Core`, `CxC`, `Fiscal`, `Integraciones`).
- Export **default** del componente de página.

## Anatomía de una página de LISTADO (objetivo)

```tsx
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip, type Column } from '../../../components/ui';
import { get } from '../../../services/api';
import { toList } from '../../../utils/api';
import { finanzasKeys } from '../../../lib/queryKeys';

export type Moneda = { id_moneda: string; codigo_iso: string; nombre: string; activo: boolean };

const columns: Column<Moneda>[] = [
  { key: 'codigo', header: 'Código ISO', render: (r) => r.codigo_iso },
  { key: 'nombre', header: 'Nombre',     render: (r) => r.nombre },
  { key: 'estado', header: 'Activo', align: 'center', render: (r) => <StatusChip value={r.activo} /> },
];

export default function MonedaListPage() {
  const { data: monedas = [], isLoading, isError } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: () => get('/finanzas/monedas/'),
    select: toList<Moneda>,
  });

  return (
    <PageContainer>
      <PageHeader
        title="Monedas"
        subtitle="Catálogo de monedas del sistema"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} component={Link} to="/finanzas/monedas/new">
            Nueva Moneda
          </Button>
        }
      />
      {isError ? (
        <Alert severity="error">No se pudieron cargar las monedas.</Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={monedas}
          getRowKey={(r) => r.id_moneda}
          loading={isLoading}
          onRowClick={(r) => navigate(`/finanzas/monedas/${r.id_moneda}`)}
        />
      )}
    </PageContainer>
  );
}
```

Puntos clave:
- `PageContainer` + `PageHeader` (no `<h2 style>` ni divs sueltos).
- `DataTable` maneja loading/empty; el error se muestra con `<Alert>`.
- Datos vía TanStack Query + `queryKeys` factory + `toList` (ver `omni-frontend-data`).
- Filtro/búsqueda: en listas chicas, `useState` + `.filter()` en cliente; en
  listas grandes/paginadas, pasá el término al backend como query param.

## Anatomía de una página de FORMULARIO

Ver `omni-frontend-forms` para el detalle completo (react-hook-form + zod). En
síntesis: `PageLayout maxWidth={480..720}` → `<Typography variant="h5">` →
`<Box component="form" onSubmit={handleSubmit(onSubmit)}>` → `<Stack spacing={2}>`
con `TextField`/`Controller` → botones Cancelar/Guardar a la derecha → mutación
con invalidación + navegación + feedback.

## Anatomía de una página de DETALLE

- `PageLayout` (tarjeta centrada) o `PageContainer` según densidad.
- `PageHeader` con `title` dinámico y `actions` (Editar, Anular).
- Datos read-only en una grilla (`Grid`/`Stack`) o un formulario deshabilitado.
- Acciones destructivas (anular/eliminar lógico) pasan por `useConfirm()` (ver
  `omni-frontend-forms` / FeedbackContext). Nunca `window.confirm`.

## Registrar la ruta

Cada módulo tiene su archivo de rutas en `frontend/src/routes/<modulo>Routes.tsx`,
agregadas al router en `frontend/src/router.tsx`. Las rutas autenticadas se
montan dentro de `AppLayout` (shell con sidebar/topbar/breadcrumbs/asistente).

```tsx
// routes/finanzasRoutes.tsx
import { lazy } from 'react';
const MonedaListPage   = lazy(() => import('../pages/Finanzas/Monedas/MonedaListPage'));
const MonedaFormPage   = lazy(() => import('../pages/Finanzas/Monedas/MonedaFormPage'));
const MonedaDetailPage = lazy(() => import('../pages/Finanzas/Monedas/MonedaDetailPage'));

export const finanzasRoutes = [
  { path: '/finanzas/monedas',      element: <MonedaListPage /> },
  { path: '/finanzas/monedas/new',  element: <MonedaFormPage /> },
  { path: '/finanzas/monedas/:id',  element: <MonedaDetailPage /> },
];
```

- Usá **`lazy()`** para code-splitting (el `AppLayout` ya tiene `<Suspense>`).
- Rutas en **kebab-case**, alineadas con el backend (`/finanzas/monedas/`).
- Si la ruta depende de la empresa activa, seguí el patrón
  `/empresas/${emp}/...` que ya usa la navegación.

## Registrar en la navegación

La navegación es **fuente única** en `frontend/src/config/navigation.tsx`
(`buildNavigation(empresaId)`). Agregá tu entrada en la sección correcta:

```tsx
{ id: 'finanzas', label: 'Finanzas', icon: <AccountBalanceWalletOutlined />, items: [
  { label: 'Monedas', path: '/finanzas/monedas' },
  // ...
]},
```

No hardcodees menús en otros componentes; todos consumen `buildNavigation`.

## Scoping multi-tenant (R-CODE-1)

Toda página opera sobre la **empresa activa**. El backend ya filtra por empresa,
pero el frontend debe pasar el contexto cuando aplica:
- `getEmpresaId()` (de `utils/empresa`) para el id de empresa activa.
- Incluí `empresaId` en la `queryKey` cuando la data depende de la empresa, para
  que el caché no mezcle tenants (ver `finanzasKeys.monedas.empresaActivas(id)`).
- Nunca asumas "todas las empresas": una pantalla que lista datos de varias
  empresas es un bug de aislamiento.

## i18n

Los textos visibles deberían pasar por `react-i18next` (`useTranslation`) cuando
la pantalla sea parte del flujo internacionalizable. Para pantallas internas en
español, mantené consistencia con el resto (es la default). Ver
`omni-frontend-i18n-l10n`.

## Errores comunes a evitar

### Error 1: Reinventar el shell
**Mal:** una página que arma su propio sidebar/header.
**Bien:** montarla dentro de `AppLayout` vía routes; usar `PageHeader`.

### Error 2: Tabla/inputs HTML crudos
**Mal:** `<table style>` + `<input>` + `<Link style={{background:'#1976d2'}}>`.
**Bien:** `DataTable` + `TextField` + `<Button component={Link}>`.

### Error 3: Olvidar registrar en navegación
La ruta funciona por URL directa pero no aparece en el menú → el usuario no la encuentra.

### Error 4: Caché cruzando tenants
**Mal:** `queryKey: ['monedas']` para datos por-empresa.
**Bien:** incluir `empresaId` en la key.

### Error 5: No manejar loading/empty/error
La página parpadea o muestra "undefined". Contemplá los tres estados.

### Error 6: Lógica de negocio/montos a mano en la página
Cálculos de dinero con `+`/`*` de JS. Usá los helpers de `omni-money-ui`.

## Checklist antes de cerrar

- [ ] Archivos en `pages/<Modulo>/<Entidad>/` con sufijo `Page` y export default.
- [ ] `PageContainer`/`PageHeader` (listado) o `PageLayout` (form/detalle).
- [ ] Datos vía TanStack Query + `queryKeys` + `toList`/`toCount`.
- [ ] Estados loading / empty / error.
- [ ] Ruta registrada con `lazy()` en `routes/<modulo>Routes.tsx`.
- [ ] Entrada agregada en `config/navigation.tsx`.
- [ ] Scoping por empresa activa (key + params) cuando aplica.
- [ ] Acciones destructivas vía `useConfirm`, feedback vía `useSnackbar`.
- [ ] `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- `pages/Finanzas/Monedas/*`, `routes/*Routes.tsx`, `router.tsx`,
  `config/navigation.tsx`, `components/layout/AppLayout.tsx`.
- Skills: `omni-design-system`, `omni-frontend-data`, `omni-frontend-forms`,
  `omni-money-ui`, `omni-frontend-i18n-l10n`, `omni-frontend-reskin`.

## Changelog

### v1.0 — 2026-06-03
- Versión inicial.
