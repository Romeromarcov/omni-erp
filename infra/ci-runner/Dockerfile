# ──────────────────────────────────────────────────────────────────────────
# Self-hosted GitHub Actions runner para Omni ERP en Railway (servicio `ci-runner`)
#
# Por qué existe: los runners alojados por GitHub tienen un tope de 6 h por job.
# Para suites/cargas que deben correr HORAS o DÍAS sin depender de tu laptop ni
# de una sesión de Claude, este runner —siempre encendido en Railway— ejecuta
# esos jobs (los workflows que apuntan a `runs-on: [self-hosted, omni]`).
#
# Despliegue y variables: ver infra/ci-runner/README.md.
# Modelo de trabajo completo: docs/ENTORNO_DE_TRABAJO.md
# ──────────────────────────────────────────────────────────────────────────
FROM ubuntu:24.04

ARG RUNNER_VERSION=2.321.0
ENV DEBIAN_FRONTEND=noninteractive

# ── Toolchain de Omni (Python 3.11 vía deadsnakes, Node 22, cliente Postgres) ──
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates git jq ripgrep build-essential \
        software-properties-common gnupg libicu-dev \
        postgresql-client \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# El runner de GitHub no puede ejecutarse como root.
RUN useradd -m runner
WORKDIR /home/runner/actions-runner

RUN curl -fsSL -o runner.tar.gz \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" \
    && tar xzf runner.tar.gz \
    && rm runner.tar.gz \
    && ./bin/installdependencies.sh \
    && chown -R runner:runner /home/runner

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER runner
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
