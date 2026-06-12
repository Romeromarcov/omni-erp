# Runbook — Backups de PostgreSQL y prueba de restore (P0-9 / Plan 05 P1-7)

> **Estado:** la infraestructura está COMPLETA en el repo (workflow diario de backup,
> script con retención de 30 días, y workflow semanal de **restore test automatizado**).
> Lo único que falta es **operativo del owner**: crear el bucket y cargar los secrets
> en GitHub (los secrets no puede crearlos un agente). Son ~10 minutos, una sola vez.

## Qué hay en el repo

| Pieza | Archivo | Qué hace |
|---|---|---|
| Backup diario | `.github/workflows/backup.yml` | 06:00 UTC: `pg_dump` comprimido → S3 con SSE, retención 30 días. Se omite (sin fallar) si faltan secrets. |
| Script de backup | `infra/backup/pg_dump_omni.sh` | Dump + verificación de tamaño + subida + retención. |
| **Restore test semanal** | `.github/workflows/restore-test.yml` | Lunes 07:00 UTC: baja el ÚLTIMO backup del bucket, lo restaura en un Postgres efímero del runner y valida ≥50 tablas y antigüedad <48h. Falla ruidosamente si el backup diario dejó de correr. |
| Simulacro local | `infra/backup/restore_dryrun.sh` | Restore manual a una BD temporal (lo usa el workflow). |

## Lo que TÚ tienes que hacer (una vez, ~10 min)

### Paso 1 — Datos de la BD de producción (Railway)
1. Railway → proyecto **Omni-ERP** → environment **production** → servicio **Postgres** → pestaña **Variables/Connect**.
2. Copia los valores del **TCP proxy público** (no el `.railway.internal`):
   - `PGHOST` público (ej. `xxxxx.proxy.rlwy.net`) → será `BACKUP_DB_HOST`
   - Puerto del proxy (ej. `12345`) → `BACKUP_DB_PORT`
   - `PGDATABASE` → `BACKUP_DB_NAME` · `PGUSER` → `BACKUP_DB_USER` · `PGPASSWORD` → `BACKUP_DB_PASSWORD`

### Paso 2 — Bucket S3 (recomendado: Cloudflare R2, gratis hasta 10 GB)
1. Cloudflare → R2 → **Create bucket** → nombre `omni-erp-backups`.
2. R2 → **Manage API Tokens** → crear token con permiso *Object Read & Write* sobre ese bucket.
3. Anota: **Access Key ID**, **Secret Access Key** y el **endpoint** (`https://<account_id>.r2.cloudflarestorage.com`).
   - (Si prefieres AWS S3: crea el bucket + un IAM user con `s3:PutObject/GetObject/ListBucket/DeleteObject` y deja `BACKUP_S3_ENDPOINT` vacío.)

### Paso 3 — Cargar los secrets en GitHub
GitHub → repo `omni-erp` → **Settings → Secrets and variables → Actions → New repository secret**, uno por uno:

| Secret | Valor |
|---|---|
| `BACKUP_DB_HOST` | host público del proxy (Paso 1) |
| `BACKUP_DB_PORT` | puerto del proxy |
| `BACKUP_DB_NAME` | nombre de la BD |
| `BACKUP_DB_USER` | usuario |
| `BACKUP_DB_PASSWORD` | contraseña |
| `BACKUP_S3_BUCKET` | `omni-erp-backups` |
| `BACKUP_S3_ENDPOINT` | endpoint R2 (vacío/omitir si usas AWS S3) |
| `BACKUP_AWS_ACCESS_KEY_ID` | access key del token |
| `BACKUP_AWS_SECRET_ACCESS_KEY` | secret del token |
| `BACKUP_AWS_REGION` | `auto` para R2 (o la región AWS) |

### Paso 4 — Primera corrida y verificación (5 min)
1. GitHub → **Actions → "Backup — PostgreSQL (GAP-4-bis)" → Run workflow**. Debe terminar verde y dejar un `.sql.gz` en el bucket.
2. **Actions → "Restore test — backup de PostgreSQL (P1-7)" → Run workflow**. Verde = restore REAL probado (restaura el dump en un Postgres limpio y valida la estructura). 
3. Con ambos verdes: marca **P0-9 cerrado** (este runbook + la corrida fechada son la evidencia que pide el plan).

## Operación continua (ya automática)
- Backup **diario** 06:00 UTC con retención de 30 días.
- Restore test **semanal** (lunes) que además **alerta si el backup diario lleva >48h sin correr**.
- Si un lunes falla el restore test: revisa el log del job — o el backup diario dejó de subir, o el dump está corrupto. Ambos casos son accionables desde Actions sin tocar producción.

## Restore real a producción (solo en desastre)
1. Baja el dump deseado del bucket.
2. Railway → crea un servicio Postgres NUEVO (no pises el actual hasta validar).
3. `gunzip -c dump.sql.gz | psql <DATABASE_URL_del_nuevo>` y valida con la app apuntando a esa BD en un environment de prueba.
4. Cambia `DATABASE_URL` del backend de producción al nuevo Postgres. Nunca restaurar encima de la BD viva.
