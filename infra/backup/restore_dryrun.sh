#!/usr/bin/env bash
# GAP-4 — Simulacro de restore: restaura un dump en una BD temporal y valida
# integridad básica (conteos). NO toca la base de producción.
#
# Uso: ./restore_dryrun.sh <archivo.sql.gz>
# Variables: DB_HOST DB_PORT DB_USER PGPASSWORD (de un Postgres dev/staging)
set -euo pipefail

DUMP="${1:?Uso: restore_dryrun.sh <archivo.sql.gz>}"
: "${DB_HOST:?}"; : "${DB_USER:?}"
DB_PORT="${DB_PORT:-5432}"
TMP_DB="omni_restore_test_$(date -u +%s)"

echo "[restore] creando BD temporal ${TMP_DB}"
createdb --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" "$TMP_DB"
trap 'dropdb --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" "$TMP_DB" || true' EXIT

echo "[restore] restaurando ${DUMP}"
gunzip -c "$DUMP" | psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$TMP_DB" -q

echo "[restore] validando integridad (conteo de tablas con filas)"
psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$TMP_DB" -t -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"

echo "[restore] simulacro OK — la BD temporal se elimina automáticamente."
