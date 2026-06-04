---
name: omni-frontend-data
description: Use this skill whenever the frontend fetches, caches, or mutates server data in the Omni ERP. Triggers include "carga los datos de X", "agrega un endpoint al frontend", working with TanStack Query (useQuery/useMutation), the `services/api.ts` verbs (get/post/patch/put/del), DRF pagination normalization (toList/toCount), the `lib/queryKeys.ts` factory, cache invalidation, or multi-tenant query scoping. Do NOT use for pure visual/layout work or backend API implementation.
---

# Skill: Fetching y Estado de Servidor en el Frontend de Omni

## Cuándo usar esta skill

Cargá esta skill cuando una pantalla **lee o escribe datos del backend**:
listados, detalles, selectores de catálogo, mutaciones de alta/edición/anulación.

Stack: **TanStack Query v5** sobre el fetcher propio `services/api.ts`. El
`QueryClient` se configura en `lib/queryClient.ts` y se monta en `App.tsx`.

## Capa de transporte: `services/api.ts`

Usá **siempre** los verbos del módulo, nunca `fetch`/`axios` directo en páginas:

```ts
import { get, post, patch, put, del } from '../services/api';

await get<Moneda[]>('/finanzas/monedas/');
await post('/finanzas/monedas/', payload);
await patch(`/finanzas/monedas/${id}/`, cambios);
await del(`/finanzas/monedas/${id}/`);
```

Lo que `api.ts` ya resuelve por vos (no lo reimplementes):
- **Auth:** token de acceso **en memoria** (nunca en localStorage) + cookie
  httpOnly de refresh. Header `Authorization: Bearer` automático.
- **Refresh 401 + retry una vez:** una sola promesa de refresh compartida; N
  401s concurrentes esperan el mismo refresh. Si falla → `signalLogout()`.
- **Timeout/abort:** 30 s por defecto (90 s para blob/SSE).
- **Errores:** lanza `Error` con el cuerpo JSON del backend serializado; detecta
  respuestas HTML (endpoint mal configurado) y da un mensaje claro.
- **Texto/Blob/SSE:** `fetchText`, `fetchBlob` (descargas/PDF) y `streamSSE`
  (respuestas en streaming del asistente). Reusan el mismo pipeline de auth.

Endpoints: paths relativos que empiezan con `/` (se les antepone `API_URL`). No
hardcodees `http://localhost`; eso lo maneja `resolveApiUrl()` (falla rápido en
prod si falta `VITE_API_URL`).

## Normalización de respuestas DRF

El backend puede responder **lista directa** o **paginada**
(`{ count, next, previous, results }`). Normalizá SIEMPRE con los helpers de
`utils/api.ts`:

```ts
import { toList, toCount } from '../utils/api';

const { data: monedas = [] } = useQuery({
  queryKey: finanzasKeys.monedas.all(),
  queryFn: () => get('/finanzas/monedas/'),
  select: toList<Moneda>,        // ← array garantizado, nunca undefined
});
```

- `toList<T>(raw)` → `T[]` (array directo o `.results`, o `[]`).
- `toCount(raw)` → número total (para paginación).
- Usá `select` para que el componente reciba ya el array (no toques `.results` en
  el JSX).

## Query keys: factory central

NO uses strings sueltos como key. Todas las keys viven en `lib/queryKeys.ts`,
agrupadas por dominio con prefijos jerárquicos:

```ts
import { finanzasKeys, ventasKeys, cxcKeys, inventarioKeys } from '../lib/queryKeys';

finanzasKeys.monedas.all()                 // ['finanzas','monedas']
finanzasKeys.monedas.detail(id)            // ['finanzas','monedas', id]
finanzasKeys.monedas.empresaActivas(empId) // por-empresa (incluye empId)
ventasKeys.cotizaciones.all()
```

- **Invalidá por prefijo:** invalidar `['finanzas','monedas']` afecta lista y
  detalle. Por eso las familias comparten prefijo estable.
- **Agregá tu key a la factory** cuando creás un recurso nuevo; no la inventes
  inline en la página.

## Multi-tenant en el caché (R-CODE-1)

Si la data depende de la empresa activa, **incluí el `empresaId` en la key**:

```ts
const empresaId = getEmpresaId() || '';
useQuery({
  queryKey: ventasKeys.productos(empresaId),
  queryFn: () => fetchProductos(empresaId),
  enabled: !!empresaId,           // no dispares sin empresa
});
```

Sin esto, el caché podría servir datos de otra empresa al cambiar de tenant →
fuga de aislamiento. Las factories `*(empresaId?)` ya están pensadas para esto.

## Mutaciones

```ts
const queryClient = useQueryClient();
const mutation = useMutation({
  mutationFn: (payload: Record<string, unknown>) => post('/finanzas/monedas/', payload),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: finanzasKeys.monedas.all() });
    snackbar.success('Creado correctamente.');
  },
  onError: () => snackbar.error('No se pudo crear.'),
});
mutation.mutate(payload);   // usá mutation.isPending para deshabilitar UI
```

- Siempre **invalidar** las queries afectadas en `onSuccess`.
- Feedback de éxito/error vía `useSnackbar` (ver `omni-frontend-forms`).
- Para listas optimistas, usá `onMutate`/`onError`/`onSettled` solo si hace falta;
  el default (invalidar) es suficiente en la mayoría de casos.

## Hook genérico `useApiQuery`

Para lecturas simples sin transformación, existe `hooks/useApiQuery.ts`:

```ts
const { data, isLoading, error } = useApiQuery<Empresa[]>('/core/empresas/');
```

Úsalo para casos triviales; para data por-empresa o con `select`, preferí
`useQuery` directo con la `queryKeys` factory (más explícito y cacheable mejor).

## Patrón de carga de catálogos / referencia

Para selects que dependen de otros campos (p. ej. sucursales de la empresa
elegida), encadená con `enabled` + key derivada y `staleTime`:

```ts
const sucursalesQuery = useQuery({
  queryKey: ['venta-ref', 'sucursales', empresaId],
  queryFn: () => get(`/core/sucursales/?id_empresa=${empresaId}`),
  enabled: !!empresaId,
  staleTime: 60_000,        // catálogos cambian poco
});
```

## Errores comunes a evitar

### Error 1: `fetch`/`axios` directo en una página
**Mal:** `await fetch('/api/...')`. **Bien:** `get/post/...` de `services/api`.
**Por qué:** perdés auth, refresh, timeout y manejo de error centralizados.

### Error 2: Tocar `.results` en el JSX
**Mal:** `data?.results?.map(...)`. **Bien:** `select: toList` y mapear el array.

### Error 3: Key string suelta / duplicada
**Mal:** `queryKey: ['monedas']` en 5 archivos distintos.
**Bien:** `finanzasKeys.monedas.all()`.

### Error 4: Caché sin empresa
**Mal:** key sin `empresaId` para datos por-tenant. **Bien:** incluir `empresaId`.

### Error 5: No invalidar tras mutar
La UI queda desactualizada. Invalidá en `onSuccess`.

### Error 6: Guardar tokens en localStorage
**Prohibido.** El access token va en memoria; el refresh es cookie httpOnly. Ya
está resuelto en `api.ts`; no lo "mejores" persistiéndolo.

### Error 7: Tragar errores con `catch {}`
Al menos mostrá feedback (`snackbar.error`) o `<Alert>`; no dejes al usuario sin
señal de que algo falló.

## Checklist antes de cerrar

- [ ] Transporte vía `services/api` (get/post/patch/put/del), no fetch/axios.
- [ ] Respuestas normalizadas con `toList`/`toCount`.
- [ ] Keys desde `lib/queryKeys.ts` (agregadas a la factory si son nuevas).
- [ ] `empresaId` en la key cuando la data es por-empresa + `enabled`.
- [ ] Mutaciones invalidan caché + feedback éxito/error.
- [ ] Sin tokens en localStorage; sin `catch {}` mudo.
- [ ] `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- `services/api.ts`, `utils/api.ts`, `lib/queryKeys.ts`, `lib/queryClient.ts`,
  `hooks/useApiQuery.ts`, `hooks/useDocumentoVentaBase.ts`, `utils/empresa.ts`.
- Skills: `omni-frontend-page`, `omni-frontend-forms`, `omni-frontend-i18n-l10n`.
- Plan maestro §3.5 (respuesta paginada DRF, `toList`/`toCount`).

## Changelog

### v1.0 — 2026-06-03
- Versión inicial.
