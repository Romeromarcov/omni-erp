# Backups de PostgreSQL — Omni ERP (GAP-4 / GAP-4-bis)

Estrategia dual, coherente con las dos topologías de deploy:

- **Railway (primaria):** el addon Postgres trae backups gestionados por la
  plataforma. Verificá en el dashboard la frecuencia/retención del plan. Si la
  retención no cubre el RPO fiscal VE (objetivo ≥ 30 días), el workflow
  programado `.github/workflows/backup.yml` hace un `pg_dump` propio y lo sube a
  un bucket S3 externo (no Railway) — **GAP-4-bis**.
- **Self-hosted (futuro):** correr `pg_dump_omni.sh` como sidecar/cron del
  `docker-compose.prod.yml` — **GAP-4**.

## Scripts

- `pg_dump_omni.sh` — dump comprimido (`gzip -9`), subida opcional a S3 con
  `--sse AES256`, retención configurable (`BACKUP_RETENTION_DAYS`, default 30).
- `restore_dryrun.sh <archivo.sql.gz>` — **simulacro de restore**: restaura en
  una BD temporal y valida integridad; la BD temporal se elimina al terminar.
  Nunca toca producción.

## Variables

`DB_HOST DB_PORT DB_NAME DB_USER PGPASSWORD` y, para subir a S3:
`BACKUP_S3_BUCKET AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION`
(+ `BACKUP_S3_ENDPOINT` para MinIO/R2).

## Programación (GitHub Actions)

`.github/workflows/backup.yml` corre `schedule: cron` diario. Está **guardado**:
si no hay `secrets.BACKUP_DB_HOST`, el job se omite limpiamente (no falla), igual
que el workflow de deploy. Configurar los secrets para activarlo.

## Healthcheck

El workflow falla (y por ende notifica) si el dump resulta sospechosamente
pequeño. Para alertar sobre backups vencidos (> 25 h), conectar la salida del
workflow a Sentry/notificación o usar el monitor de cron de Sentry.

## DoD

Ejecutar `restore_dryrun.sh` contra el último dump sobre una instancia dev y
verificar que restaura y reporta conteos sin error.
