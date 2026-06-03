# Despliegue en Railway — Omni ERP

> Guía para desplegar Omni ERP en Railway (servidor primario activo para pruebas humanas
> reales). Railway construye desde los **Dockerfiles** vía integración con GitHub.

## Servicios a crear en el proyecto Railway

| Servicio | Fuente | Notas |
|---|---|---|
| **backend** | `backend/Dockerfile` (root dir = `backend/`) | uvicorn ASGI; entrypoint corre migraciones + collectstatic |
| **frontend** | `frontend/Dockerfile.prod` (root dir = `frontend/`) | nginx sirve el build; ya trae headers de seguridad |
| **Postgres** | plugin Railway | provee `DATABASE_URL` |
| **Redis** | plugin Railway | provee `REDIS_URL` (Celery / caché) |

> Celery worker/beat: servicios adicionales con el mismo `backend/Dockerfile` pero
> `CMD` override a `celery -A config worker` / `celery -A config beat`.

## Variables de entorno (servicio backend)

**Obligatorias (el backend falla-cerrado si faltan):**

| Variable | Valor en Railway | Por qué |
|---|---|---|
| `DJANGO_ENV` | `prod` | activa `settings_prod` (HSTS, collectstatic, etc.) |
| `SECRET_KEY` | (generar, secreto) | Django; sin esto no arranca |
| `CRYPTOGRAPHY_KEY` | (generar Fernet, secreto) | cifrado en reposo |
| `DJANGO_ALLOWED_HOSTS` | dominio Railway, p.ej. `omni-erp-production.up.railway.app` | `ALLOWED_HOSTS` es fail-closed en prod |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | conexión BD (parseado nativamente) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Celery / caché |

**Recomendadas:**

| Variable | Valor | Por qué |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | URL del frontend Railway | CORS |
| `SENTRY_DSN` | (tu DSN) | observabilidad de errores en prod |
| `USE_S3` + `S3_*` | si usás MinIO/S3 | almacenamiento de archivos |
| `REFRESH_TOKEN_COOKIE_SAMESITE` | `None` si frontend en dominio distinto | cookie de refresh cross-site |

**Frontend:** `VITE_API_BASE_URL` = URL pública del backend Railway (en build).

## Puntos ya resueltos (compatibilidad Railway)

- **Puerto dinámico:** el `CMD` usa `${PORT:-8000}` — Railway inyecta `$PORT` y enruta a él.
  (Antes fijaba `8000` → fallaba el healthcheck/routing de Railway.)
- **`DATABASE_URL`:** `settings_base` parsea `DATABASE_URL` (Railway/Heroku) con prioridad,
  con fallback a `DB_*` para dev local.

## Diagnóstico de logs

```bash
railway logs            # logs del servicio seleccionado (build + runtime)
railway logs --deployment <id>
railway status
railway variables       # verificar que las vars obligatorias estén
```

Errores típicos y causa:
- **`ImproperlyConfigured: DJANGO_ALLOWED_HOSTS ...`** → falta `DJANGO_ALLOWED_HOSTS`.
- **`SECRET_KEY environment variable is not set`** → falta `SECRET_KEY`.
- **healthcheck failed / app no responde** → puerto (ya resuelto) o `DJANGO_ALLOWED_HOSTS`
  no incluye el dominio Railway (Django responde 400 "Bad Request (Invalid HTTP_HOST)").
- **`could not connect to server` / `role does not exist`** → `DATABASE_URL` no enlazado al
  plugin Postgres.
- **`relation ... does not exist`** → faltan migraciones (el entrypoint las corre; revisar el
  log de arranque).

> **Nota:** `.github/workflows/deploy.yml` es para despliegue **self-hosted vía SSH/systemd**,
> NO para Railway. En Railway el deploy lo dispara el push a `main` (integración GitHub) o
> `railway up`. No hace falta ese workflow para Railway.
