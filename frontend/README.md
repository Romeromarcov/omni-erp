# Frontend — Omni ERP

React 19 + TypeScript + Vite + MUI v7 · PWA · i18n · TanStack Query

## Stack

| Componente | Tecnología | Notas |
|---|---|---|
| Framework | React 19 | Concurrent mode |
| Lenguaje | TypeScript (strict) | `tsc -b` en build |
| Build tool | Vite 7 | HMR, PWA via vite-plugin-pwa |
| UI Library | MUI v7 | Componentes MUI directamente (sin wrappers) |
| Routing | React Router v7 | Rutas por dominio: `coreRoutes`, `ventasRoutes`, etc. |
| Estado servidor | TanStack Query v5 | `useQuery` / `useMutation` en todas las páginas |
| i18n | react-i18next | `src/i18n/locales/es.json` + `en.json` |
| Auth | Context API (`AuthContext`) | JWT via SimpleJWT backend |
| Tests | Vitest + Testing Library | `src/__tests__/`, 29+ tests passing |
| PWA | vite-plugin-pwa | Service worker + manifest |
| CI | GitHub Actions | `tsc --noEmit` + ESLint en cada PR |

## Comandos principales

```bash
# Instalar dependencias
npm install

# Desarrollo local (hot reload)
npm run dev

# Build de producción (type-check + vite build)
npm run build

# Linter
npm run lint

# Tests con Vitest
npx vitest run

# Tests con cobertura
npx vitest run --coverage
```

## Estructura

```
src/
├── __tests__/          # Vitest — tests de páginas y utilidades
├── components/         # Componentes reutilizables (PageLayout, Pedidos/*, etc.)
├── hooks/              # Hooks de formularios (useDocumentoVentaBase, usePedidoForm, …)
├── i18n/
│   └── locales/        # es.json, en.json
├── pages/
│   ├── Core/           # Login, Empresas, Usuarios, Departamentos
│   ├── Finanzas/       # Monedas, TasasCambio, MetodoPago, CajaFísica, …
│   └── Ventas/         # Cotizaciones, Pedidos, NotasVenta, FacturasFiscales
├── services/           # Capa HTTP — get/post/patch/fetcher de api.ts
├── types/              # Interfaces TypeScript por dominio
└── utils/              # toList, toCount y helpers de paginación
```

## Variables de entorno

```bash
# .env.local (no subir al repo)
VITE_API_URL=http://localhost:8000
```

Sin esta variable, `src/services/api.ts` usa `/api` relativo (funciona con el proxy de Vite).

## i18n

El idioma activo se guarda en `localStorage('lang')`. Namespace principal: `translation`.

Claves organizadas por dominio:
- `common.*` — acciones y mensajes genéricos
- `nav.*` — menú lateral
- `auth.*` — login
- `ventas.tabla.*` / `ventas.pedidos.*` / `ventas.facturas.*` / `ventas.notasVenta.*`

Para agregar claves: editar `src/i18n/locales/es.json` y `en.json` en paralelo.

## Tests

Los tests usan `MemoryRouter + QueryClientProvider + I18nextProvider` (inicializado en `src/test-setup.ts`).

Mock estándar:
```typescript
vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetcher: vi.fn(),
}));
```

## CI

El workflow `.github/workflows/ci.yml` ejecuta en cada PR:
- `tsc --noEmit` — 0 errores de tipado requeridos
- `npm run lint` — ESLint (errores bloquean el job)
- `npm run build` — `tsc -b && vite build`
