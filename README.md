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

## Documentación

- Plan maestro del proyecto: `OMNI_ERP_MASTER_PLAN.md`
- API interactiva: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/

## Contribución

- Usa ramas `feature/` o `bugfix/` para tus cambios.
- Asegúrate de que los tests y linters pasen antes de hacer PR.
- Lee el `OMNI_ERP_MASTER_PLAN.md` antes de incorporarte al proyecto.

---

¿Dudas? Consulta el plan maestro o contacta al equipo de desarrollo.
