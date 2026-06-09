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

# ── Frontend (Node + npm) ──
if [ -f "$ROOT/frontend/package.json" ]; then
  echo "[session-start] Instalando dependencias de frontend…"
  ( cd "$ROOT/frontend" && npm install --no-audit --no-fund )
fi

echo "[session-start] Entorno listo."
