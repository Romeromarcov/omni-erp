# E2E Playwright — flujos críticos (TEST-6 / Fase 4)

Specs end-to-end contra la UI real + backend real. Cada spec siembra **sus**
datos vía API (con sufijo único por corrida) sobre la base que crea
`seed_empresa_inicial`; son re-ejecutables contra una BD persistente.

## Specs

| Spec | Flujo | Acción crítica | Verificación en UI |
|---|---|---|---|
| `login.smoke.spec.ts` | Smoke de login (sin backend) | render del formulario | pantalla de login |
| `venta.flow.spec.ts` | Venta: pedido → confirmar | confirmación vía API (sin botón en UI) | listado/detalle de pedido, stock comprometido, dashboard CxC |
| `cxc-abono.flow.spec.ts` | Cobro/abono CxC | abono vía API (sin formulario en UI) | Dashboard de Cartera (saldo actualizado) |
| `caja.flow.spec.ts` | Caja (sustituye compras, que es API-only) | pago efectivo vía API | pagos del pedido + movimientos de caja |
| `inventario.flow.spec.ts` | Ajuste de inventario | **100 % UI** (pantalla de ajustes) | Stock Actual + Kardex |
| `login-multiempresa.flow.spec.ts` | Login + selección multi-empresa | **100 % UI** | dashboard + navegación por módulos |

Los pasos que se hacen vía API en lugar de UI corresponden a **gaps reales del
producto** (botones que llaman endpoints inexistentes, formularios ausentes);
están documentados en el encabezado de cada spec.

## Cómo correrlos localmente

```bash
# 1. Backend con BD Postgres migrada (puerto 8000)
cd backend
python manage.py migrate

# 2. Seed: 2 empresas + admin compartido (multi-empresa). Idempotente.
export OMNI_SEED_ADMIN_PASSWORD='<una-contraseña-que-pase-los-validadores>'
python manage.py seed_empresa_inicial --nombre-legal "Empresa E2E Uno C.A." --rif "J-11111111-1" \
  --admin-username admin_e2e --admin-email admin.e2e@example.com
python manage.py seed_empresa_inicial --nombre-legal "Empresa E2E Dos C.A." --rif "J-22222222-2" \
  --admin-username admin_e2e --admin-email admin.e2e@example.com
python manage.py runserver 0.0.0.0:8000

# 3. Frontend — build de producción servido con preview (igual que CI)
cd frontend
VITE_API_URL=http://localhost:8000/api npm run build
npm run preview -- --port 4173

# 4. Playwright
npx playwright install chromium   # una vez
E2E_BASE_URL=http://localhost:4173 \
E2E_ADMIN_PASSWORD="$OMNI_SEED_ADMIN_PASSWORD" npm run test:e2e
```

> ⚠️ Corre los flujos contra el **build de producción** (`preview`), igual que
> CI. Con el dev server (`npm run dev`, StrictMode) los efectos dobles disparan
> dos `token/refresh` concurrentes y, con la rotación + blacklist de refresh
> tokens, la sesión muere de forma intermitente.

Variables:

- `E2E_BASE_URL` — URL del frontend (default `http://localhost:5173`).
- `E2E_ADMIN_USER` — usuario admin del seed (default `admin_e2e`).
- `E2E_ADMIN_PASSWORD` — contraseña del seed (obligatoria; nunca en código, R-CODE-8).

## Notas de diseño

- **Serie, no paralelo** (`workers: 1`): los flujos comparten la BD del backend
  y el login tiene rate-limit (SEC-07, 5/min por IP).
- **Empresa primaria**: los documentos creados vía API caen en la primera
  empresa visible ordenada por `nombre_legal` (`EmpresaInjectMixin` +
  `Empresa.Meta.ordering`); los helpers seleccionan esa misma empresa en la UI.
- En CI el job `e2e` (no-bloqueante, Fase 5 lo endurecerá) levanta Postgres,
  backend, build+preview del frontend y corre esta suite completa.
- **BD local que crece**: las páginas de stock/productos solo consumen la
  primera página del API (PAGE_SIZE 20, gap de UI sin paginación). La suite es
  re-ejecutable mientras la BD tenga <20 filas de stock; si tu `omni_e2e` local
  se llenó de corridas viejas, recréala (drop + migrate + seed). En CI la BD
  siempre nace limpia.
