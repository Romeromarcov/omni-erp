# Despliegue en Railway — Omni ERP

> Estado: **operativo** en el proyecto Railway `laudable-eagerness`
> (`f5c956c3-39dd-4b0c-9e9f-25f14283463d`), environment `production`.
> Railway construye desde los **Dockerfiles** vía integración con GitHub (rama `main`).

## Servicios (proyecto nuevo)

| Servicio | Root Directory | Dockerfile (vía `railway.toml`) | Puerto | Dominio |
|---|---|---|---|---|
| **omni-erp-backend** | `backend` | `Dockerfile` | 8000 | https://omni-erp-backend-production.up.railway.app |
| **omni-erp-frontend** | `frontend` | `Dockerfile.prod` (nginx) | 8080 | https://omni-erp-frontend-production.up.railway.app |
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
> NO para Railway. En Railway el deploy lo dispara el push a `main` (integración GitHub).
