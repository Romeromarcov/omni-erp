#!/bin/bash
# SessionStart hook — prepara el entorno de Omni ERP para sesiones de
# Claude Code en la web (instala dependencias de backend y frontend).
# Documentación del modelo de trabajo: docs/ENTORNO_DE_TRABAJO.md
set -euo pipefail

# Solo en el entorno remoto (Claude Code en la web). En local no tocamos nada.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# ── Backend (Python 3.11 + venv) ──
# Usamos un virtualenv para aislar dependencias y evitar el setuptools
# parcheado del Python del sistema (que rompe algunos wheels).
if [ -f "$ROOT/backend/requirements-dev.txt" ]; then
  echo "[session-start] Instalando dependencias de backend…"
  VENV="$ROOT/backend/.venv"
  if [ ! -d "$VENV" ]; then
    python -m venv "$VENV"
  fi
  "$VENV/bin/pip" install --upgrade pip setuptools wheel >/dev/null
  "$VENV/bin/pip" install -r "$ROOT/backend/requirements-dev.txt"
  # Persistimos el venv para toda la sesión (PATH + activación).
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    echo "export VIRTUAL_ENV=\"$VENV\"" >> "$CLAUDE_ENV_FILE"
    echo "export PATH=\"$VENV/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  fi
fi

# ── PostgreSQL de pruebas (espejo de CI; R-CODE-2: nunca SQLite) ──
# Solo aplica cuando la BD es local (contenedor de Claude web, que trae
# PostgreSQL instalado pero apagado). En el devcontainer DB_HOST=db (servicio
# de compose) y esta sección se omite completa.
DB_TARGET_HOST="${DB_HOST:-localhost}"
if [ "$DB_TARGET_HOST" = "localhost" ] || [ "$DB_TARGET_HOST" = "127.0.0.1" ]; then
  if command -v pg_isready >/dev/null 2>&1; then
    if ! pg_isready -h localhost -p 5432 -q 2>/dev/null; then
      echo "[session-start] Arrancando PostgreSQL local…"
      service postgresql start 2>/dev/null || sudo service postgresql start 2>/dev/null || true
    fi
    if pg_isready -h localhost -p 5432 -q 2>/dev/null; then
      # Usuario y BD idempotentes (CREATEDB: pytest crea su propia BD de test).
      sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='omni_erp'" 2>/dev/null | grep -q 1 \
        || sudo -u postgres psql -c "CREATE USER omni_erp WITH PASSWORD 'omni_erp_dev' CREATEDB;" || true
      sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='omni_erp'" 2>/dev/null | grep -q 1 \
        || sudo -u postgres psql -c "CREATE DATABASE omni_erp OWNER omni_erp;" || true
      echo "[session-start] PostgreSQL listo (BD omni_erp)."
    else
      echo "[session-start] AVISO: PostgreSQL no disponible — los tests de backend no podrán correr." >&2
    fi
  fi
fi

# ── backend/.env de desarrollo ──
# Solo si DJANGO_ENV no viene ya del entorno (el devcontainer lo define en
# compose) y el .env no existe. El .env está en .gitignore: nunca se commitea.
if [ -z "${DJANGO_ENV:-}" ] && [ ! -f "$ROOT/backend/.env" ]; then
  echo "[session-start] Generando backend/.env de desarrollo…"
  SECRET_KEY="$("$ROOT/backend/.venv/bin/python" -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())' 2>/dev/null \
    || head -c 50 /dev/urandom | base64 | tr -d '=+/')"
  cat > "$ROOT/backend/.env" <<EOF
DJANGO_ENV=dev
SECRET_KEY=$SECRET_KEY
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DB_HOST=localhost
DB_PORT=5432
DB_NAME=omni_erp
DB_USER=omni_erp
DB_PASSWORD=omni_erp_dev
EOF
fi
# DJANGO_ENV como variable de sesión: algunos scripts leen el entorno del
# proceso sin pasar por dotenv.
if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -z "${DJANGO_ENV:-}" ]; then
  echo 'export DJANGO_ENV=dev' >> "$CLAUDE_ENV_FILE"
fi

# ── Frontend (Node + npm) ──
if [ -f "$ROOT/frontend/package.json" ]; then
  echo "[session-start] Instalando dependencias de frontend…"
  ( cd "$ROOT/frontend" && npm install --no-audit --no-fund )
fi

echo "[session-start] Entorno listo."
