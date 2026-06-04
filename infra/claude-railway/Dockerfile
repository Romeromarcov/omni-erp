# ──────────────────────────────────────────────────────────────────────────
# Claude Code en Railway — contenedor de desarrollo interactivo
#
# Este servicio NO sirve tráfico web: es una "caja de desarrollo" siempre
# encendida a la que entras con `railway ssh` para abrir sesiones de Claude
# Code directamente sobre el repositorio, ejecutándose en la nube de Railway
# (no en la nube de Claude).
#
# Uso (tras desplegar):
#   railway ssh --service claude-dev
#   cd /workspace/omni-erp && claude
# ──────────────────────────────────────────────────────────────────────────
FROM node:22-bookworm

# ── Herramientas de sistema que Claude Code y el flujo de trabajo necesitan ──
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        python3 \
        python3-pip \
        python3-venv \
        build-essential \
        curl \
        ca-certificates \
        ripgrep \
        less \
        jq \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub CLI (para `gh auth login` / clonar / abrir PRs desde la sesión) ──
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ── Claude Code CLI ──────────────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code

# El workspace vive en un VOLUMEN de Railway montado en /workspace para que el
# repositorio clonado y el estado de Claude sobrevivan a los redeploys.
ENV WORKSPACE=/workspace
WORKDIR /workspace

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
