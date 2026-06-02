# Frontend — Omni ERP

React 19 + TypeScript + Vite + MUI v7 · PWA · i18n · TanStack Query

> **Estado: refactor en pausa.** La estructura actual (stack, routing por dominio, páginas, componentes, hooks, servicios, i18n, auth, tests y CI) está documentada aquí y refleja el árbol vigente de `src/`. Si el refactor se retoma y reorganiza páginas/rutas, actualizar las tablas de "Dominios", "Componentes" y "Hooks".

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
├── assets/             # Recursos estáticos
├── components/         # Componentes reutilizables (PageLayout, SidebarMenu, Pedidos/*, …)
├── config/             # Configuración del cliente
├── contexts/           # AuthContext (JWT), AssistantContext (asistente IA)
├── hooks/              # Hooks de datos y formularios (useCxC, useDocumentoVentaBase, usePedidoForm, …)
├── i18n/ + i18n.ts     # locales/ → es.json, en.json
├── lib/                # Utilidades de bajo nivel
├── pages/              # Páginas por dominio (refactor en curso, ver abajo)
├── router.tsx          # Composición del router raíz
├── routes/             # Rutas por dominio: coreRoutes, ventasRoutes, cxcRoutes, … (un archivo por módulo)
├── schemas/            # Esquemas de validación por dominio (ventas, compras, fiscal)
├── services/           # Capa HTTP — api.ts + un servicio por recurso (ver servicios)
├── types/              # Interfaces TypeScript por dominio
└── utils/              # toList, toCount y helpers de paginación
```

### Dominios (pages/ + routes/)

El routing está dividido por dominio en `src/routes/*.tsx` (compuestos en `src/router.tsx`), cada uno mapeado a un directorio en `src/pages/`. La mayoría de los recursos siguen el patrón **List / Detail / Create|Form** page.

| Dominio | Rutas | Páginas (`src/pages/`) |
|---|---|---|
| **Core** | `coreRoutes` | `Login/` (LoginPage, DashboardUserPage), `Empresas/` (List·Detail·Create), `Sucursales/` (List·Detail·Create), `Departamentos/` (List·Detail·Create), `Usuarios/` (UserList·Detail·Create, RoleList·Detail·Create, PermissionList, ProfilePage), `Auditoria/` (AuditLogList) |
| **Ventas** | `ventasRoutes` | `Cotizaciones/`, `Pedidos/`, `NotasVenta/`, `FacturasFiscales/`, `NotasCreditoVenta/`, `NotasCreditoFiscal/`, `DevolucionesVenta/` — cada uno con List·Detail·Form |
| **CxC** | `cxcRoutes` | DashboardCxCPage, CobranzaPage, AcuerdosPage, AgenteCobranzaPage |
| **Finanzas** | `finanzasRoutes` | `Monedas/`, `TasasCambio/`, `MetodoPago/`, `TransaccionFinanciera/`, `Cajas/` (Caja, CajaFisica, Movimientos, PlantillasMaestro, OverridesMetodosPago), `CuentasBancarias/` (List·Detail·Create·Movimientos) |
| **Fiscal** | `fiscalRoutes` | ConfiguracionFiscalPage, LibroVentasPage, LibroComprasPage |
| **Inventario** | `inventarioRoutes` | InventarioDashboardPage, StockActualPage, KardexPage, AjusteInventarioPage |
| **Configuración** | `configuracionRoutes` | `TiposDocumento/`, `ParametrosSistema/`, `CatalogosValor/` — cada uno List·Detail |
| **Integraciones** | `integracionesRoutes` | IntegrationHubPage, ConectorDetallePage, ConectorCard, NuevoConectorModal |

## Componentes (`src/components/`)

| Grupo | Componentes | Rol |
|---|---|---|
| Layout | `layout/AppLayout`, `Sidebar`, `Topbar`, `AppBreadcrumbs`, `PageLayout` | Estructura de página y navegación. |
| UI base | `ui/DataTable`, `PageContainer`, `PageHeader`, `StatusChip`, `Pagination` | Primitivas reutilizables sobre MUI. |
| Ventas | `Pedidos/*` (TablaProductos, FormularioCliente/Producto, ModalBusquedaCliente/Producto, ModalPago, ResumenPago/Totales/Vuelto, SeccionNotasCredito, CamposDinamicos) | Piezas del formulario de documentos de venta. |
| Auth/usuarios | `LoginForm`, `ProfileForm`, `RoleList`, `DeviceActionModal` | Login, perfil, roles y acción de dispositivo. |
| Asistente IA | `assistant/AssistantDrawer`, `assistant/Markdown`, `SugerenciasWidget` | UI del asistente y sugerencias de agentes. |
| Otros | `DashboardCard`, `NotificationBell`, `ModalBusqueda` | Tarjetas de dashboard, notificaciones, búsqueda genérica. |

## Hooks (`src/hooks/`)

| Hook | Rol |
|---|---|
| `useApiQuery` | Acceso HTTP y wrappers de TanStack Query. |
| `useDocumentoVentaBase` | Lógica común a todos los documentos de venta. |
| `usePedidoForm`, `useCotizacionForm`, `useNotaVentaForm`, `useFacturaFiscalForm` | Estado/validación de cada formulario de venta. |
| `useCxC` | Datos del módulo de cobranza. |
| `useAssistantChat` | Conversación con el asistente IA. |

Otros directorios: `contexts/` (`AuthContext` JWT, `AssistantContext`), `config/navigation.tsx` (definición del menú), `lib/queryClient.ts` (cliente TanStack Query), `schemas/` (validación por dominio).

### Capa de servicios

`src/services/api.ts` centraliza el cliente HTTP (`get`/`post`/`patch`/`fetcher`) con el token JWT. Cada recurso del backend tiene un servicio dedicado (p. ej. `clientesService.ts`, `pagosService.ts`, `inventarioService.ts`, `fiscalService.ts`, `integrationHubService.ts`). Ver [`services/README_PagosService.md`](src/services/README_PagosService.md) para el caso detallado del servicio de pagos.

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
