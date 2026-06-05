# Despliegue en Railway — Omni ERP

> Estado: **operativo** en el proyecto Railway `Omni-ERP`
> (`f5c956c3-39dd-4b0c-9e9f-25f14283463d`).
> Railway construye desde los **Dockerfiles** vía integración con GitHub.
>
> **Dos entornos (ver [`FLUJO_DE_TRABAJO.md`](FLUJO_DE_TRABAJO.md)):**
> - `main` → environment **production** (deploy automático al merge).
> - `develop` → environment **staging** (Postgres/Redis propios, aislados de prod).
>
> Un feature pasa por **develop (staging) → main (prod)**; un fix/hotfix puede ir directo
> a `main` (con PR) y luego sincronizar `develop`.

## Servicios (proyecto nuevo)

| Servicio | Root Directory | Dockerfile (vía `railway.toml`) | Puerto | Dominio |
|---|---|---|---|---|
| **omni-erp-backend** | `backend` | `Dockerfile` | 8000 | https://omni-erp-backend-production.up.railway.app |
| **omni-erp-frontend** | `frontend` | `Dockerfile.prod` (nginx) | 8080 | https://omni-erp-frontend-production.up.railway.app |
| **omni-erp-celery-worker** | `backend` | `Dockerfile` (vía `railway.worker.toml`) | — (no HTTP) | — (sin dominio) |
| **omni-erp-celery-beat** | `backend` | `Dockerfile` (vía `railway.beat.toml`) | — (no HTTP) | — (sin dominio) |
| **Postgres** | — (plugin) | — | 5432 | `postgres.railway.internal` |
| **Redis** | — (plugin) | — | 6379 | `redis.railway.internal` |

- Health backend: `GET /api/health/` → `{"status":"ok"}`.
- **Config-as-code:** cada servicio trae un `railway.toml` (en `backend/` y `frontend/`)
  que fija `builder = "DOCKERFILE"` y el Dockerfile correcto. **Imprescindible** fijar el
  **Root Directory** de cada servicio en el dashboard (`backend` / `frontend`); sin él
  Railway intenta construir la raíz del monorepo con el autodetect (RAILPACK) y falla.

## Variables del backend (no commitear secretos)

| Variable | Valor | Nota |
|---|---|---|
| `DJANGO_ENV` | `prod` | activa `settings_prod` (DEBUG=False, HSTS, etc.) |
| `SECRET_KEY` | (secreto) | sin esto no arranca |
| `CRYPTOGRAPHY_KEY` | (Fernet, secreto) | cifrado en reposo |
| `DJANGO_ALLOWED_HOSTS` | `omni-erp-backend-production.up.railway.app,.railway.app` | fail-closed en prod |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | conexión BD |
| `DB_HOST` / `DB_PORT` | `${{Postgres.PGHOST}}` / `${{Postgres.PGPORT}}` | el `entrypoint.sh` espera la BD por `DB_HOST` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Celery / caché |
| `CORS_ALLOWED_ORIGINS` | dominio del frontend | CORS |
| `REFRESH_TOKEN_COOKIE_SAMESITE` | `None` | frontend en subdominio distinto |
| `USE_S3` | `False` | almacenamiento local por ahora |
| `PORT` | `8000` | el contenedor escucha `${PORT}` |

**Frontend:** `VITE_API_URL` = `https://omni-erp-backend-production.up.railway.app/api`
(se incrusta en el build de Vite; Railway lo pasa como build-arg).

## Servicios Celery (worker + beat)

Las tareas en segundo plano (sync de tasas BCV, limpieza de logs, auditoría, etc.)
las corre **Celery**, no el web. Hacen falta **dos servicios nuevos** en Railway que
**reusan el mismo `backend/Dockerfile`** del web pero arrancan con un comando distinto:

- **worker** — procesa las tareas. Escucha las colas **`celery`** y **`auditoria`**.
- **beat** — scheduler periódico. Usa `django_celery_beat` (**DatabaseScheduler**).

Sin estos dos servicios, las tareas se encolan en Redis pero **nadie las ejecuta** ni
las programa (que es el síntoma actual: el sync BCV y la limpieza de logs no corren).

### Cómo lo arranca Railway (Dockerfile compartido + startCommand)

El `backend/Dockerfile` define `ENTRYPOINT ["/app/entrypoint.sh"]` + `CMD <uvicorn…>`.
Railway, vía el `startCommand` del config-as-code, **sustituye sólo el `CMD`** (no el
`ENTRYPOINT`). Es decir: el `entrypoint.sh` **se sigue ejecutando** y al final hace
`exec "$@"` con el comando de celery. Cada servicio trae su propio config:

| Archivo | Servicio | startCommand |
|---|---|---|
| `backend/railway.worker.toml` | worker | `python -m celery -A config worker --loglevel=info --concurrency=2 --queues=celery,auditoria --hostname=worker@%h` |
| `backend/railway.beat.toml` | beat | `python -m celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler` |

Ambos fijan `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` y
`restartPolicyType = "ON_FAILURE"` (mismo estilo que `backend/railway.toml`). **No**
declaran healthcheck HTTP porque celery no sirve HTTP.

### ⚠️ Worker y beat NO re-ejecutan migraciones

Como el `entrypoint.sh` corre igual, **sin guarda** worker y beat re-correrían
`migrate` + `collectstatic` en cada arranque/reinicio → **carrera de migraciones** con
el web y arranques lentos. Para evitarlo, `entrypoint.sh` reconoce la variable
**`SKIP_MIGRATIONS=1`**: cuando está, omite `migrate`, `create_initial_data` y
`collectstatic`, y arranca directo el proceso de celery. **Las migraciones las aplica
sólo el servicio web.** Por eso worker y beat **deben** definir `SKIP_MIGRATIONS=1`.

Las tablas que necesita beat (`django_celery_beat`, ya en `INSTALLED_APPS` y en
`requirements.txt`) y los resultados (`django_celery_results`) los crea el web al migrar,
así que para cuando beat arranque ya existen.

### Variables de entorno (worker y beat)

Son **las mismas del backend** salvo que **NO necesitan `PORT` ni dominio público**
(no sirven HTTP) y **sí** deben llevar `SKIP_MIGRATIONS=1`:

| Variable | Valor | Nota |
|---|---|---|
| `DJANGO_ENV` | `prod` | mismo settings que el web |
| `SECRET_KEY` | (secreto) | igual que el backend |
| `CRYPTOGRAPHY_KEY` | (Fernet, secreto) | cifrado en reposo |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | conexión BD |
| `DB_HOST` / `DB_PORT` | `${{Postgres.PGHOST}}` / `${{Postgres.PGPORT}}` | el `entrypoint.sh` espera la BD por `DB_HOST` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | **broker + backend de Celery (imprescindible)** |
| `SKIP_MIGRATIONS` | `1` | **clave**: que NO migren (sólo migra el web) |
| `DJANGO_ALLOWED_HOSTS` | `.railway.app` | no sirven HTTP, pero settings lo lee al cargar |
| `USE_S3` | igual que el backend | si las tareas tocan ficheros |

> No definir `PORT`, ni dominio público, ni healthcheck HTTP. **No** poner `RUN_SEED=1`
> (el seed lo hace —si acaso— el web).

### Pasos en el dashboard de Railway (uno por servicio)

Repetir para **worker** y para **beat** (cambiando el config file):

1. En el proyecto `laudable-eagerness` → **New → GitHub Repo** → mismo repo del backend.
2. **Settings → Source**: fija **Root Directory = `backend`** (igual que el web; sin esto
   Railway intenta el autodetect RAILPACK en la raíz del monorepo y falla).
3. **Settings → Build**: en **Config-as-code / Railway Config File** apunta a
   `railway.worker.toml` (servicio worker) o `railway.beat.toml` (servicio beat).
   El `startCommand` ya viene en ese archivo; no hace falta tocar el Custom Start Command.
   *(Alternativa si tu plan no soporta config file por servicio: deja el config en
   blanco y pega el comando de celery correspondiente en **Custom Start Command**.)*
4. **Variables**: copia las del backend (puedes usar **Reference Variables** a Postgres/
   Redis igual que el web) y **añade `SKIP_MIGRATIONS=1`**. Quita `PORT` si se copió.
5. **No** generes dominio público (Settings → Networking: sin Public Networking).
6. Deploy. Verifica en logs: worker debe mostrar `celery@worker… ready` y las colas
   `celery, auditoria`; beat debe mostrar `beat: Starting…` y `DatabaseScheduler`.

> **beat = una sola instancia.** No escales el servicio beat a >1 réplica: duplicaría las
> tareas programadas. El worker sí puede escalar horizontalmente sin problema.

## Causa raíz del bloqueo histórico (DisallowedHost / "DEBUG en prod")

El backend respondía `DisallowedHost` con página de DEBUG en el dominio público **aunque
`DJANGO_ENV=prod`**. No era un "contenedor zombi" de Railway: era un **bug de código**.

- `config/__init__.py` importa `config.celery` al cargar el paquete `config`.
- `config/celery.py` hacía `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")`.
- Al arrancar el servidor (`uvicorn config.asgi:application`), importar `config.asgi`
  carga primero el paquete `config` → corre `celery.py` → fija el módulo a `settings_dev`.
  El `setdefault("config.settings")` de `asgi.py`/`wsgi.py` quedaba como no-op.
- Resultado: **uvicorn cargaba `settings_dev` (DEBUG=True, ALLOWED_HOSTS de dev) en producción**.
  `manage.py` no importa el paquete `config`, por eso `migrate`/`collectstatic` sí usaban prod
  (de ahí la confusión: los logs de arranque mostraban `settings_prod`, pero el server servía dev).

**Fix:** `config/celery.py` ahora usa el dispatcher `config.settings` (igual que asgi/wsgi);
`DJANGO_ENV` decide dev/prod de forma coherente en todos los procesos.

## Otras decisiones de despliegue

- **Sin healthcheck HTTP de Railway** en el backend: `settings_prod` fuerza
  `SECURE_SSL_REDIRECT=True`, y el probe interno (HTTP a `healthcheck.railway.app`) no
  devolvía 200, marcando el deploy como FAILED pese a estar sano. La salud de contenedor
  la cubre el `HEALTHCHECK` del Dockerfile (curl a `localhost`); el tráfico real entra por
  el dominio público (sí está en `ALLOWED_HOSTS`).
- **Seed inicial:** `entrypoint.sh` corre `create_initial_data` (empresa + superusuario
  `admin`) solo si `RUN_SEED=1`. Se activa una vez en un entorno nuevo y luego se deja en `0`.
  ⚠️ La contraseña por defecto (`admin123`) **debe cambiarse** tras el primer login.

## Diagnóstico rápido (CLI)

```bash
npx -y @railway/cli status                              # servicios y estado
npx -y @railway/cli deployment list --service <id>      # historial de deploys
npx -y @railway/cli logs --service <id> --deployment <full-id>
npx -y @railway/cli variables --service <id> --kv       # variables (¡no exponer secretos!)
```

> **Nota:** `.github/workflows/deploy.yml` es para despliegue self-hosted vía SSH/systemd,
> NO para Railway. En Railway el deploy lo dispara el merge a la rama del entorno:
> **`main` → producción**, **`develop` → staging** (integración GitHub). Para investigar un
> entorno sin desplegar, usa la skill `docs/skills/diagnostico-railway/` (solo lectura).
