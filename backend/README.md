# Backend — Omni ERP

Django 4.x + Django REST Framework · Multi-tenant · API-first

## Stack

| Componente | Tecnología | Notas |
|---|---|---|
| Framework | Django 4.x | `config/settings_base.py`, `config/settings_dev.py` |
| API | Django REST Framework 3.x | Swagger en `/api/docs/` |
| Auth | SimpleJWT | `/api/token/`, `/api/token/refresh/` |
| Filtros | django-filter 25.x | `DjangoFilterBackend` en todos los ViewSets |
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

```
apps/
├── core/           # Empresa, Usuario, Rol, Permiso, Dispositivo, CajaFísica
├── ventas/         # Cotización, Pedido, NotaVenta, FacturaFiscal, MCP tools
├── finanzas/       # Moneda, TasaCambio, Pago, CajaFísica, MCP tools
├── inventario/     # Producto, StockActual, MCP tools
├── configuracion_motor/  # TipoDocumento, ParametroSistema, CatalogoValor
├── auditoria/      # LogAuditoria (signals automáticos)
├── compras/        # OrdenCompra (backend sin UI)
├── manufactura/    # ListaMateriales, OrdenProduccion (parcial)
└── ...             # ~20 apps adicionales en distintas etapas
```

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
