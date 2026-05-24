#!/bin/sh
set -e

# Exportar defaults para que Django los vea si no vienen del entorno
export DB_HOST="${DB_HOST:-db}"
export DB_PORT="${DB_PORT:-5432}"

if [ -n "$DB_HOST" ]; then
    echo "Waiting for postgres at ${DB_HOST}:${DB_PORT}..."
    MAX_RETRIES=30
    RETRIES=0
    while ! nc -z "${DB_HOST}" "${DB_PORT}"; do
        RETRIES=$((RETRIES + 1))
        if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
            echo "Error: PostgreSQL did not start in time" >&2
            exit 1
        fi
        sleep 1
    done
    echo "PostgreSQL started"
fi

echo "Applying database migrations..."
python manage.py migrate --noinput

# collectstatic solo en prod — en dev uvicorn sirve estáticos directamente
# y el volume mount genera conflictos de permisos con el usuario no-root
if [ "${DJANGO_ENV}" = "prod" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
else
    echo "Skipping collectstatic (DJANGO_ENV=${DJANGO_ENV:-dev})"
fi

echo "Starting server..."
exec "$@"
