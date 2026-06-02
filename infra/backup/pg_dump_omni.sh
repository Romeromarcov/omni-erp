#!/usr/bin/env bash
# GAP-4 / GAP-4-bis — Backup de PostgreSQL de Omni ERP.
#
# Hace pg_dump comprimido y, si hay credenciales S3, lo sube a un bucket con
# cifrado SSE-S3. Pensado para correr en un sidecar (docker-compose.prod) o en
# un job programado de GitHub Actions (ver .github/workflows/backup.yml).
#
# Variables requeridas:
#   DB_HOST DB_PORT DB_NAME DB_USER PGPASSWORD
# Opcionales (subida a S3):
#   BACKUP_S3_BUCKET  (ej. omni-erp-backups)
#   AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION
#   BACKUP_S3_ENDPOINT (para MinIO/R2)
#   BACKUP_RETENTION_DAYS (default 30)
set -euo pipefail

: "${DB_HOST:?DB_HOST requerido}"
: "${DB_NAME:?DB_NAME requerido}"
: "${DB_USER:?DB_USER requerido}"
DB_PORT="${DB_PORT:-5432}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${BACKUP_OUT_DIR:-/tmp/omni-backups}"
mkdir -p "$OUT_DIR"
OUT_FILE="${OUT_DIR}/omni_${DB_NAME}_${STAMP}.sql.gz"

echo "[backup] pg_dump ${DB_NAME}@${DB_HOST}:${DB_PORT} → ${OUT_FILE}"
pg_dump --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
        --no-owner --no-privileges --format=plain "$DB_NAME" \
  | gzip -9 > "$OUT_FILE"

SIZE="$(wc -c < "$OUT_FILE")"
if [ "$SIZE" -lt 1024 ]; then
  echo "[backup] ERROR: dump sospechosamente pequeño (${SIZE} bytes)" >&2
  exit 1
fi
echo "[backup] OK (${SIZE} bytes)"

if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  ENDPOINT_ARG=""
  [ -n "${BACKUP_S3_ENDPOINT:-}" ] && ENDPOINT_ARG="--endpoint-url ${BACKUP_S3_ENDPOINT}"
  echo "[backup] subiendo a s3://${BACKUP_S3_BUCKET}/ (SSE-S3)"
  aws s3 cp $ENDPOINT_ARG --sse AES256 "$OUT_FILE" "s3://${BACKUP_S3_BUCKET}/$(basename "$OUT_FILE")"
  # Retención: borra objetos más viejos que RETENTION_DAYS.
  CUTOFF="$(date -u -d "-${RETENTION_DAYS} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-"${RETENTION_DAYS}"d +%Y-%m-%dT%H:%M:%SZ)"
  aws s3api list-objects-v2 $ENDPOINT_ARG --bucket "$BACKUP_S3_BUCKET" \
    --query "Contents[?LastModified<'${CUTOFF}'].Key" --output text 2>/dev/null \
    | tr '\t' '\n' | while read -r key; do
        [ -n "$key" ] && aws s3 rm $ENDPOINT_ARG "s3://${BACKUP_S3_BUCKET}/${key}" || true
      done
  echo "[backup] retención aplicada (> ${RETENTION_DAYS} días eliminados)"
fi

echo "[backup] completado: $(basename "$OUT_FILE")"
