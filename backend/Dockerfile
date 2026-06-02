# NEW-INFRA-3: multi-stage build — builder compiles wheels, runtime stays lean
# Base image pinned to a specific digest-stable tag (NEW-INFRA-3)

# ── Stage 1: builder — compiles Python wheels ──────────────────────────────
FROM python:3.11.10-slim-bookworm AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

COPY requirements.txt /wheels/
RUN pip wheel --no-cache-dir --wheel-dir /wheels/dist -r requirements.txt

# ── Stage 2: runtime — only what is needed to run ──────────────────────────
FROM python:3.11.10-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        libpq5 \
        netcat-traditional \
        dos2unix \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install wheels built in builder stage (no build tools needed at runtime)
COPY --from=builder /wheels/dist /wheels/dist
RUN pip install --no-cache-dir --no-index --find-links=/wheels/dist /wheels/dist/* \
    && rm -rf /wheels

COPY . /app/

# dos2unix + chmod deben ir DESPUÉS de COPY . /app/: ese COPY sobrescribe
# entrypoint.sh con el archivo del repo y borra el bit de ejecución, por lo
# que el appuser no-root no podía ejecutar el entrypoint y el contenedor
# fallaba al arrancar.
RUN dos2unix /app/entrypoint.sh && chmod +x /app/entrypoint.sh

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && mkdir -p /app/logs /app/staticfiles \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# NEW-INFRA-5: healthcheck (curl is installed in runtime stage)
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 CMD curl -fsS http://localhost:8000/api/health/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
