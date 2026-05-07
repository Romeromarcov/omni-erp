#!/bin/sh
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

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

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"
