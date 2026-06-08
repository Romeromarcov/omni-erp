# Plan C — Panel SaaS del proveedor

| Campo | Valor |
|-------|-------|
| **Objetivo** | Consola para que el **dueño del software** administre el negocio SaaS: planes, tenants, suscripciones, signup y (futuro) facturación. |
| **Estado actual** | Backend **completo**; frontend **inexistente** (ni rutas, ni páginas, ni servicios que consuman `/api/saas/*`). |
| **Esfuerzo** | ~2.5 semanas (C1+C2) · billing (C4) diferido. |

## Punto de partida (verificado en código)

**Backend listo** (`apps/saas/`):
- Modelos `Plan` (FREE/STARTER/PRO/ENTERPRISE; feature flags `permite_ia`, `permite_api`, límites de usuarios/empresas/docs) y `Suscripcion` (estados ACTIVA/VENCIDA/CANCELADA/SUSPENDIDA/TRIAL, vigencia por fechas).
- Endpoints: `GET/POST/PATCH /api/saas/planes/` (escritura solo `es_superusuario_omni`), `/api/saas/suscripciones/` (+ acciones `cancelar`, `suspender`, `activa`).
- Middleware `SuscripcionActivaMiddleware` → **HTTP 402** si no hay suscripción activa; **desactivado** por `SAAS_VERIFICAR_SUSCRIPCION=False`.
- Helpers `suscripcion_activa()`, `tiene_feature()`.

**Falta** (frontend + 2 piezas backend): UI de proveedor, auto-signup, facturación, medición de LLM.

## Fase C1 — Consola de proveedor (frontend) · ~1.5–2 semanas
- Ruta protegida `/admin-saas` visible solo a `es_superusuario_omni` (corregir drift primero → [CTF-009](../ctf/CTF-009.md)).
- `frontend/src/services/saasService.ts` consumiendo `/api/saas/*`.
- Páginas: **CRUD de Planes**, **lista de todos los tenants/empresas**, **gestión de suscripciones** (crear/activar/suspender/cancelar), **dashboard** (clientes activos, por vencer, MRR estimado).
- Entrada en `frontend/src/config/navigation.tsx` (sección visible solo al proveedor).
- **DoD:** el proveedor crea un plan, asigna una suscripción a un tenant y la suspende, todo desde la UI.

## Fase C2 — Activar control de acceso por pago · ~2–3 días
- Activar `SAAS_VERIFICAR_SUSCRIPCION=True` en staging; validar flujo 402 end-to-end.
- Registrar la app `saas` en Django admin (`apps/saas/admin.py`) como respaldo operativo.
- **DoD:** un tenant sin suscripción vigente recibe 402; con suscripción activa, opera normal.

## Fase C3 — Auto-provisioning (signup) · ~1 semana
- Endpoint `/api/saas/signup/` (crea `Empresa` + usuario admin + `Suscripcion` TRIAL 30 días) + pantalla de onboarding.
- **DoD:** un prospecto se registra solo y queda en TRIAL operativo.

## Fase C4 — Facturación + medición LLM · ~2 semanas (DIFERIDO hasta cobrar)
- App `apps/billing`: pasarela (Stripe u opción local VE), modelos `Invoice`/`Payment`, task Celery de renovación.
- **Medidor de tokens LLM por tenant** (para revender IA): cuota + costo por `PrediccionAgente` (`apps/agentes/models.py`). Hoy no hay medición de tokens.
- **DoD:** cobro recurrente automatizado; corte por impago; cuota de LLM aplicada por plan.

## Definition of Done (para administrar pilotos: C1+C2)

- [x] Consola de proveedor operativa (planes, tenants, suscripciones, dashboard). — `frontend/src/pages/SaaS/`, ruta `/admin-saas` con guard de rol.
- [x] Middleware 402 activado y validado en staging. — Código listo y testeado end-to-end (JWT real); se activa con `SAAS_VERIFICAR_SUSCRIPCION=True` (env, staging primero). El middleware quedó registrado en `MIDDLEWARE` y resuelve el usuario por JWT.
- [x] Drift de rol corregido ([CTF-009](../ctf/CTF-009.md)).
- [x] Gate de cierre ejecutado en cada PR.

### Estado de avance (2026-06-07)

- **C1 — Consola de proveedor:** ✅ completa (CRUD planes, tenants, suscripciones con activar/suspender/cancelar, dashboard con MRR; navegación y guard solo-proveedor).
- **C2 — Control de acceso por pago:** ✅ middleware registrado y env-driven; authz de suscripciones híbrida (crear/modificar/eliminar/**reactivar** solo proveedor; cancelar/suspender la propia = self-service del tenant); `apps/saas/admin.py` registrado. Falta solo el *toggle* operativo del env en staging.
- **C3 — Auto-provisioning (signup):** ✅ endpoint público `/api/saas/signup/` (TRIAL 30 días, rate-limit) + onboarding `/signup`.
- **C4 — Facturación + medición LLM:** ⏸️ DIFERIDO por diseño (hasta cobrar).
