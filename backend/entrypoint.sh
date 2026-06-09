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

# SKIP_MIGRATIONS=1 lo usan los servicios celery worker/beat: comparten este
# mismo ENTRYPOINT (el startCommand de Railway sólo sustituye al CMD, no al
# ENTRYPOINT), pero NO deben re-correr migraciones ni collectstatic. Migrar es
# tarea exclusiva del servicio web: hacerlo en worker/beat causa carreras de
# migración y arranques lentos. Con la variable sin definir, el web migra normal.
if [ "${SKIP_MIGRATIONS}" = "1" ]; then
    echo "SKIP_MIGRATIONS=1: omito migrate/seed/collectstatic (servicio worker/beat)."

    # Beat con DatabaseScheduler sincroniza CELERY_BEAT_SCHEDULE en las tablas
    # django_celery_beat_* al arrancar; si esas tablas aún no existen (entorno
    # NUEVO donde el servicio web todavía no terminó de migrar) el scheduler
    # revienta en el boot y el deploy queda FAILED (observado en los entornos de
    # preview por-PR de Railway). Beat NO debe migrar (lo hace el web), pero sí
    # puede ESPERAR a que las migraciones estén aplicadas. `migrate --check` es
    # de solo lectura (no aplica nada) y sale != 0 mientras queden migraciones
    # de ese app sin aplicar. En prod/entornos ya migrados pasa al instante.
    case "$*" in
        *beat*)
            echo "Beat: esperando a que el servicio web aplique las migraciones de django_celery_beat..."
            _beat_retries=0
            _beat_max=60   # ~120 s de cortesía (2 s × 60) antes de arrancar igual
            until python manage.py migrate django_celery_beat --check >/dev/null 2>&1; do
                _beat_retries=$((_beat_retries + 1))
                if [ "$_beat_retries" -ge "$_beat_max" ]; then
                    echo "Beat: timeout esperando migraciones de django_celery_beat; arranco de todos modos." >&2
                    break
                fi
                sleep 2
            done
            echo "Beat: tablas de django_celery_beat listas."
            ;;
    esac

    echo "Starting process..."
    exec "$@"
fi

echo "Applying database migrations..."
python manage.py migrate --noinput

# Seed demo opcional e idempotente, SOLO para entornos de desarrollo. Activar con
# RUN_SEED=1 en un entorno nuevo para crear la empresa y el superusuario demo. El
# comando create_initial_data está bloqueado fuera de DEBUG (crea admin/admin123),
# así que en prod este bloque no siembra nada aunque RUN_SEED=1 (|| true lo absorbe).
# Para sembrar una empresa en PRODUCCIÓN usar:
#   python manage.py seed_empresa_inicial --nombre-legal ... --rif ... (ver docs/planes/runbook-arranque-piloto.md)
if [ "${RUN_SEED}" = "1" ]; then
    echo "RUN_SEED=1: ejecutando create_initial_data (dev-only, idempotente)..."
    python manage.py create_initial_data || true
fi

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
