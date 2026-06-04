#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Entrypoint del contenedor de desarrollo "claude-dev" en Railway.
#
# 1. Clona el repositorio en el volumen persistente la primera vez.
# 2. Deja el contenedor vivo (sleep infinity) para poder entrar con
#    `railway ssh` y ejecutar `claude` de forma interactiva.
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="${GIT_REPO_URL:-https://github.com/Romeromarcov/omni-erp.git}"
TARGET="${WORKSPACE:-/workspace}/omni-erp"

if [ ! -d "${TARGET}/.git" ]; then
  echo "[claude-railway] Clonando ${REPO_URL} en ${TARGET} ..."
  git clone "${REPO_URL}" "${TARGET}" \
    || echo "[claude-railway] AVISO: el clon falló; podrás clonar manualmente tras 'railway ssh'."
else
  echo "[claude-railway] Repositorio ya presente en ${TARGET} (volumen persistente)."
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[claude-railway] AVISO: ANTHROPIC_API_KEY no está definida — 'claude' pedirá login."
else
  echo "[claude-railway] ANTHROPIC_API_KEY detectada — 'claude' usará la API key."
fi

cat <<'BANNER'
──────────────────────────────────────────────────────────────────────────
 Contenedor claude-dev listo.
 Para abrir una sesión de Claude Code sobre el repo:

     railway ssh --service claude-dev
     cd /workspace/omni-erp && claude

──────────────────────────────────────────────────────────────────────────
BANNER

# Mantener el contenedor en ejecución para railway ssh.
exec sleep infinity
