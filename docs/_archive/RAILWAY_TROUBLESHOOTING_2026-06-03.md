# Troubleshooting despliegue Railway — 2026-06-03 (archivado)

> Bitácora del paréntesis de despliegue en Railway. Resuelve el crash del backend y deja
> diagnosticado un bloqueo de propagación de variables de Railway. Complementa la guía viva
> [`docs/DESPLIEGUE_RAILWAY.md`](../DESPLIEGUE_RAILWAY.md).

## Contexto

- Proyecto Railway **Omni-ERP**, environment `production`.
- Servicios: `frontend` (Online), `backend` (estaba **Crashed**), `Postgres` (Online).
- **No hay servicio Redis ni MinIO** (las vars `REDIS_URL`/`S3_ENDPOINT_URL` apuntan a hosts
  de docker-compose que no existen en Railway).
- Acceso: Railway CLI vía `npx @railway/cli` con un **Project Token** (`RAILWAY_TOKEN`).
  El `railway ssh` NO funciona con project token ("Unauthorized").

## Problemas encontrados y su estado

### 1. Backend crasheaba al arrancar — ✅ RESUELTO
**Log:** `ImproperlyConfigured: DJANGO_ALLOWED_HOSTS debe definir al menos un host en producción`
(`settings_prod.py:9`). La variable `DJANGO_ALLOWED_HOSTS` estaba **definida pero vacía** (`''`).
Fail-closed de producción → no arranca. Tras darle valor, el backend arranca limpio
(migraciones OK, `collectstatic`, `Uvicorn running`).

### 2. `502 Application failed to respond` (dominio público) — ✅ RESUELTO (código)
El `CMD` del Dockerfile fijaba `--port 8000`; Railway enruta el dominio público a su `$PORT`
dinámico → no coincidían. **Fix en `main`** (`6f6823b`): `CMD` usa `${PORT:-8000}`. Workaround
adicional aplicado: setear `PORT=8000` en el servicio.

### 3. Backend sin dominio público — ✅ RESUELTO
`RAILWAY_PUBLIC_DOMAIN` no existía. Se generó con `railway domain`:
`https://omni-erpbackend-production.up.railway.app`.

### 4. Frontend apuntaba a `localhost` — ⚠️ PARCIAL
`VITE_API_URL = http://localhost:8000/api` (valor de dev incrustado en el build). Se cambió a
`https://omni-erpbackend-production.up.railway.app/api` (dispara rebuild del frontend). El
`Dockerfile.prod` ya acepta `VITE_API_URL` como build-arg.

### 5. `400 DisallowedHost` persistente — ⛔ BLOQUEADO (propagación de variables Railway)
Tras resolver el puerto, el dominio público devuelve `400 DisallowedHost` para
`omni-erpbackend-production.up.railway.app`, **aunque**:
- `railway variables` / `railway run` reportan `DJANGO_ALLOWED_HOSTS` con el host exacto.
- `validate_host('omni-erpbackend-production.up.railway.app', ['.railway.app'])` → `True`
  (verificado en local; el comodín y el dominio explícito SÍ matchean).
- Se desplegó código (`main` `55563c5`) que **añade `RAILWAY_PUBLIC_DOMAIN`** (variable de
  sistema) a `ALLOWED_HOSTS` — y AÚN rechaza el host.

**Conclusión:** el **contenedor en runtime NO recibe las variables que el CLI reporta**. Es un
problema de **scope/propagación de variables de Railway**, no de código.

## Hallazgos clave sobre Railway CLI + project token

- `railway variables --set` con project token **a veces no dispara un deploy nuevo** (y la API
  `backboard.railway.com/graphql` daba **timeouts** intermitentes en las escrituras).
- `railway redeploy` **reusa el snapshot de env del deploy anterior** — no recarga variables
  nuevas.
- **Un `git push` a `main` SÍ dispara un deploy fresco** con el env actual (es el trigger
  fiable). Railway está conectado al repo y auto-despliega `main`.

## Fixes que quedaron en `main` (commits)

- `6f6823b` — `Dockerfile` bind a `${PORT:-8000}` + `settings_base` soporte `DATABASE_URL`.
- `55563c5` — `settings_prod` auto-añade `RAILWAY_PUBLIC_DOMAIN`/`RAILWAY_PRIVATE_DOMAIN` a
  `ALLOWED_HOSTS`.

## Cómo cerrar el bloqueo (#5) desde el dashboard

1. Servicio **backend → Variables**. Setear/re-guardar
   `DJANGO_ALLOWED_HOSTS=omni-erpbackend-production.up.railway.app,.railway.app,omni-erp.railway.internal`.
2. Verificar que **no exista una `DJANGO_ALLOWED_HOSTS` vacía** en otro scope (shared variables
   del environment) que esté ganando en runtime.
3. **Deploy** desde el dashboard (no solo "Restart") para forzar la recarga de variables.
4. Confirmar: `https://omni-erpbackend-production.up.railway.app/api/health/` → `{"status":"ok"}`.
5. Si persiste: añadir temporalmente un log de arranque en `settings_prod` que imprima
   `os.environ.get("DJANGO_ALLOWED_HOSTS")` y `ALLOWED_HOSTS`, desplegar, y leer los logs para
   ver qué recibe REALMENTE el contenedor.

## Pendientes para "pruebas humanas reales"

- **Redis**: añadir plugin + `REDIS_URL=${{Redis.REDIS_URL}}` (si no, fallan caché/Celery).
- **MinIO/S3**: configurar bucket real o `USE_S3=False`.
- **Frontend**: tras arreglar el host, esperar su rebuild y probar login extremo a extremo.

## Seguridad

El project token usado para diagnóstico **debe revocarse** (Project Settings → Tokens → Revoke).
