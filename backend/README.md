# Backend — Omni ERP

Django 5.2 + Django REST Framework · Multi-tenant · API-first

> **Mapa completo de apps y endpoints:** [`docs/ARQUITECTURA_BACKEND.md`](docs/ARQUITECTURA_BACKEND.md). Cada app tiene además su propio `README.md` en `apps/<nombre>/`.

## Stack

| Componente | Tecnología | Notas |
|---|---|---|
| Framework | Django 5.2 | `config/settings_base.py`, `config/settings_dev.py` |
| API | Django REST Framework 3.16 | Swagger en `/api/docs/` |
| Auth | SimpleJWT | `/api/auth/token/`, `/api/auth/token/refresh/` |
| Filtros | django-filter 24.x | `DjangoFilterBackend` en los ViewSets |
| Base de datos | PostgreSQL (obligatorio) | SQLite no soportado |
| Auditoría | Django Signals → LogAuditoria | Automático en toda acción de negocio |
| MCP Server | FastMCP 1.27.x | `apps/core/mcp_server.py` — auto-discovery |
| Tests | pytest + pytest-django + pytest-cov | 600+ tests, cobertura 69% |
| CI | GitHub Actions | `.github/workflows/ci.yml` |

## Comandos principales

```bash
# Instalar dependencias
pip install -r requirements.txt

# Migraciones
python manage.py migrate

# Levantar servidor de desarrollo
python manage.py runserver

# Tests completos con cobertura
python -m pytest tests_api/ --cov=apps --cov-report=term-missing

# Generar migraciones (verificar antes de push)
python manage.py makemigrations --check
```

## Variables de entorno

Copia y completa `.env.example`:

```bash
cp .env.example .env
```

Variables obligatorias: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SECRET_KEY`.

> **Nota:** `DB_HOST` vacío lanza `ImproperlyConfigured` — PostgreSQL es requerido.

## Estructura de apps

El backend está compuesto por 36 apps Django agrupadas por dominio (núcleo, comercial, compras, inventario, finanzas, personas, integración, localización). El catálogo completo —con prefijo de routing y rol de cada app— vive en [`docs/ARQUITECTURA_BACKEND.md`](docs/ARQUITECTURA_BACKEND.md), y cada app documenta sus modelos y endpoints en su propio `apps/<nombre>/README.md`.

## Multi-tenancy

Toda tabla de negocio tiene `id_empresa` (UUID). Los ViewSets heredan de `BaseMultiTenantViewSet` que filtra automáticamente por empresas visibles del usuario autenticado.

## CI

El workflow `.github/workflows/ci.yml` corre en cada PR:
- `pytest tests_api/` con servicio PostgreSQL 17
- Coverage mínima configurada en `pytest.ini`
- `tsc --noEmit` + ESLint en el job frontend

## API Docs

Con el servidor corriendo:
- Swagger UI: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/
