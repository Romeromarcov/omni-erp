FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        build-essential \
        libpq-dev \
        netcat-traditional \
        dos2unix \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

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

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
