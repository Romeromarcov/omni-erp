# Omni ERP — Monorepo

Sistema de gestión empresarial integral, modular y escalable. Diseñado para el mercado venezolano y con visión global: multimoneda, pagos mixtos, fiscalidad adaptable y control sin rigidez contable impuesta.

## Estructura

- `backend/` — Backend Django/DRF (API REST)
- `frontend/` — Frontend web React + Vite + MUI v7
- `docker-compose.yml` — Orquestación de todos los servicios

## Levantar el stack

```bash
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- API Docs (Swagger): http://localhost:8000/api/docs/
- Base de datos: PostgreSQL en el puerto 5432

## Tests automatizados

```bash
docker compose run --rm test
```

## Variables de entorno

Copia `.env.example` a `.env` y ajusta los valores:

```bash
cp .env.example .env
```

No subas archivos `.env` reales al repositorio.

## Scripts de calidad

- Frontend: `npm run lint`, `npm run format`, `npm run test`
- Backend: `python manage.py test` o vía Docker Compose

## Desarrollo local (sin Docker)

> Docker Compose es la vía recomendada (ver arriba). Si necesitás correr el backend directamente:

**Pre-requisito:** PostgreSQL instalado y corriendo (v14+).

**Paso 1 — Clonar y configurar el entorno:**
```bash
cd backend
cp .env.example .env    # Completá DB_HOST, DB_NAME, DB_USER, DB_PASSWORD
```

**Paso 2 — Crear el usuario y la base de datos:**
```bash
# Reemplazá 5432 por tu puerto si es distinto (ej: 5433 para PG18)
createuser -h localhost -p 5432 --pwprompt omni_erp
createdb -h localhost -p 5432 -O omni_erp omni_erp
```

**Paso 3 — Instalar dependencias Python:**
```bash
pip install -r requirements.txt
```

**Paso 4 — Correr migraciones:**
```bash
python manage.py migrate
```

**Paso 5 — Levantar el servidor:**
```bash
python manage.py runserver
```

**Tests:**
```bash
python -m pytest tests_api/ -v
```

> **Nota:** SQLite no está soportado. Si `DB_HOST` está vacío, Django lanza un error con instrucciones.

## Documentación

- **Plan maestro único (fuente de verdad):** `docs/PLAN_MAESTRO_UNICO.md` — empieza aquí.
- Registro cronológico de sesiones: `backend/PROJECT_LOG.md`
- Decisiones arquitectónicas: `docs/decisions/ADR-*.md`
- Planes históricos archivados: `docs/_archive/`
- API interactiva: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/

## Contribución

- Usa ramas `feature/` o `bugfix/` para tus cambios.
- Asegúrate de que los tests y linters pasen antes de hacer PR.
- Lee `docs/PLAN_MAESTRO_UNICO.md` antes de incorporarte al proyecto.

---

¿Dudas? Consulta `docs/PLAN_MAESTRO_UNICO.md` o contacta al equipo de desarrollo.
