#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Entrypoint del self-hosted runner `ci-runner` en Railway.
#
# 1. Pide un registration token a la API de GitHub usando ACCESS_TOKEN (PAT).
# 2. Registra el runner contra el repositorio con las labels indicadas.
# 3. Lo ejecuta; al recibir SIGTERM (redeploy de Railway) se da de baja limpio.
#
# Variables (se definen en Railway, NUNCA en el repo):
#   ACCESS_TOKEN   (obligatoria)  PAT con scope `repo` para registrar el runner.
#   GH_OWNER       (def. Romeromarcov)
#   GH_REPO        (def. omni-erp)
#   RUNNER_NAME    (def. railway-ci-runner)
#   RUNNER_LABELS  (def. self-hosted,omni)
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

GH_OWNER="${GH_OWNER:-Romeromarcov}"
GH_REPO="${GH_REPO:-omni-erp}"
RUNNER_NAME="${RUNNER_NAME:-railway-ci-runner}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,omni}"

if [ -z "${ACCESS_TOKEN:-}" ]; then
  echo "[ci-runner] ERROR: falta ACCESS_TOKEN (PAT con scope 'repo')." >&2
  exit 1
fi

api="https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/actions/runners/registration-token"
echo "[ci-runner] Solicitando registration token para ${GH_OWNER}/${GH_REPO}…"
REG_TOKEN="$(curl -fsSL -X POST \
  -H "Authorization: token ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "${api}" | jq -r .token)"

if [ -z "${REG_TOKEN}" ] || [ "${REG_TOKEN}" = "null" ]; then
  echo "[ci-runner] ERROR: no se obtuvo registration token (¿PAT válido con scope repo?)." >&2
  exit 1
fi

cleanup() {
  echo "[ci-runner] Dando de baja el runner…"
  ./config.sh remove --token "${REG_TOKEN}" || true
  exit 0
}
trap cleanup INT TERM

./config.sh \
  --unattended \
  --replace \
  --url "https://github.com/${GH_OWNER}/${GH_REPO}" \
  --token "${REG_TOKEN}" \
  --name "${RUNNER_NAME}" \
  --labels "${RUNNER_LABELS}" \
  --work _work

echo "[ci-runner] Runner '${RUNNER_NAME}' registrado con labels [${RUNNER_LABELS}]. Escuchando jobs…"
./run.sh & wait $!
