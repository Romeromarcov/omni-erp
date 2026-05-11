# PROJECT_LOG — Omni ERP

Registro cronológico inmutable de sesiones de trabajo del agente IA.
Cada entrada se agrega al final. Nunca se edita ni se borra.

---

## Sesión 1 — 2026-05-10

**Rama:** `chore/diagnostico-inicial`
**Agente:** Claude (Anthropic)
**Duración estimada:** ~3 horas (continuada desde sesión anterior)
**Objetivo declarado:** Diagnóstico inicial del repositorio unificado Omni ERP. Crear infraestructura de seguimiento. Producir `docs/DIAGNOSTICO_INICIAL.md`.

### Tareas completadas

1. **Lectura de documentos fundacionales** (PASO 1):
   - `docs/AGENTE_IA_PROTOCOLO_EJECUCION.md`
   - `docs/OMNI_AI_NATIVE_EXECUTION_PLAN.md`
   - `docs/02_PLAN_EJECUCION_FOUNDER_SOLO.md`
   - `docs/01_MVP_SCOPE_NEGOCIOS_PILOTO.md`
   - `docs/OMNI_ERP_MASTER_PLAN.md` (sección 2)
   - `docs/skills/` (5 skills)

2. **Inspección del repositorio** (PASO 2):
   - Estado de builds: backend RED (django-filter faltante) → instalado temporalmente → GREEN; frontend TSC GREEN; ESLint RED (31 errores).
   - Mapa de módulos Django y páginas React completado.
   - Deuda técnica heredada verificada contra el Master Plan.
   - Dependencias instaladas vs. requeridas para Fase 0 relevadas.
   - Brechas AI-nativas identificadas.

3. **Infraestructura de seguimiento** (PASO 3):
   - `PROJECT_LOG.md` creado.
   - `docs/decisions/` creado con `.gitkeep`.
   - `docs/tech-debt/` creado con `.gitkeep`.

4. **Diagnóstico exhaustivo** (PASO 4):
   - `docs/DIAGNOSTICO_INICIAL.md` producido con 9 secciones.

5. **Entrega** (PASO 5):
   - Branch `chore/diagnostico-inicial` creado y pusheado.
   - Draft PR abierto en GitHub.

### Decisiones tomadas

- Se instaló `django-filter==24.3` en el venv local para verificar el build. No se modificó ningún archivo de requirements (deuda catalogada, no resuelta).
- No se inició ninguna construcción de Fase 0 (restricción explícita de la sesión).
- No se corrigió ningún lint error ni deuda técnica existente (solo diagnóstico).

### Hallazgos críticos

- `django-filter` no instalado en venv → backend no arranca sin intervención manual.
- Migración pendiente: `manufactura/0002_fix_codigo_unique_per_empresa`.
- 0% cobertura de tests en backend y frontend.
- `console.log/warn/error`: 85 ocurrencias en 38 archivos (Master Plan 2.3 indicaba que estaban eliminados — incorrecto).
- `ModalPago.tsx`: 1091 líneas (Master Plan indicaba ~600 — incorrecto).
- 8 brechas AI-nativas sin ningún avance: event sourcing, MCP runtime, DSL, sandbox, multi-LLM, eval suite, plano agéntico, i18n.
- Paquetes críticos faltantes en venv: `celery`, `redis`, `anthropic`, MCP SDK, `uuid7`, `redpanda-client`.

### Próximo paso recomendado

Sub-fase 1.A, semana 1: Instalar dependencias faltantes, corregir build, migrar de SQLite a PostgreSQL (local con Docker), ejecutar migración pendiente de manufactura.

---

## Sesión 2 — 2026-05-10

**Rama:** `chore/diagnostico-inicial`
**Agente:** Claude (Anthropic)
**Objetivo declarado:** Tarea #1 del orden aprobado de Sub-fase 1.A — migrar de SQLite a PostgreSQL exclusivo.

### Tareas completadas

1. **PARTE 0 — Arranque:** leído PROJECT_LOG y DIAGNOSTICO_INICIAL; verificado estado del repo (limpio, build verde, SQLite activo).
2. **PostgreSQL 18 levantado:** servicio estaba detenido; iniciado manualmente. Puerto 5433.
3. **DB y usuario creados:** `omni_erp` con `CREATEDB` privilege para pytest.
4. **settings_base.py:** eliminado bloque `else: sqlite`; reemplazado con `ImproperlyConfigured` explícito.
5. **migrate completo:** 100% de migraciones aplicadas contra PostgreSQL, incluyendo `manufactura/0002` que estaba pendiente.
6. **Fix R-CODE-1 en ClienteViewSet (crm):** `get_queryset()` devolvía todos los clientes sin filtro. Corregido a `get_empresas_visible(user)`.
7. **conftest.py reparado:** import roto `Moneda` from `core` → `finanzas`. Fixtures empresa_a/b, user_a/b añadidas.
8. **3 tests de aislamiento:** listado solo empresa propia, GET otra empresa → 404, PATCH otra empresa → 404. **6/6 PASSED**.
9. **pytest.ini:** `tests_api/` agregado a `testpaths`.
10. **.env.example y README:** documentados con setup PostgreSQL en 5 pasos.
11. **Commit y push:** `0b92dda` en `chore/diagnostico-inicial`.

### Decisiones tomadas

- Se eligió PostgreSQL 18 en puerto 5433 (instalación existente del usuario).
- Se otorgó `CREATEDB` al usuario `omni_erp` para que pytest pueda crear `test_omni_erp`.
- Se corrigió el bug R-CODE-1 en `crm/views.py` como parte de esta tarea (era un multi-tenant leak directo que habría hecho fallar los tests).
- No se instaló Docker ni se creó docker-compose.yml (es tarea #2).

### Próximo paso recomendado

Tarea #2: Setup Docker Compose con Postgres + Redis.

---

## Sesión 3 — 2026-05-10

**Rama:** `chore/diagnostico-inicial`
**Agente:** Claude (Anthropic)
**Objetivo declarado:** Tarea #2 — Setup Docker Compose con PostgreSQL + Redis.

### Tareas completadas

1. **PARTE 0 — Arranque:** repo limpio (salvo crm/models.py del task paralelo), build verde, tests 6/6.
2. **frontend/Dockerfile:** node:22-alpine, npm ci, hot reload vía volume, --host 0.0.0.0.
3. **docker-compose.yml:** 4 servicios (db, redis, backend, frontend) con healthchecks, volúmenes persistentes, hot reload para dev. db en host:5434, redis en 6379.
4. **.dockerignore (raíz):** excluye .git, venvs, node_modules, .env, docs del build context.
5. **vite.config.ts:** proxy target configurable via BACKEND_URL (default localhost:8000, Docker usa http://backend:8000).
6. **entrypoint.sh:** `export` en DB_HOST/DB_PORT para que Django vea el default.
7. **crm/models.py:** Meta.ordering = ['razon_social'] — silencia UnorderedObjectListWarning.
8. **crm/migrations/0003:** generada y aplicada.
9. **Tests:** 6/6 passed. Commit `2c455fe`, pusheado.

### Pendiente de validar (requiere Docker Desktop corriendo)

- `docker compose up db redis -d` → ambos servicios en estado `healthy`
- `docker compose up --build` → stack completo levanta sin errores
- `http://localhost:8000/api/docs/` accesible desde backend dockerizado
- `http://localhost:5173` accesible desde frontend dockerizado

### Decisiones tomadas

- PostgreSQL 17-alpine (no 18) para Docker: versión LTS más estable para imagen; el dev local del usuario usa PG18 nativo.
- DB expuesta en host:5434 para evitar colisión con PG18 nativo (5433) y PG estándar (5432).
- Hot reload en backend via `--reload --reload-dir /app` en uvicorn.
- No se creó `docker-compose.override.yml` — composición directa más simple para este punto.

### Próximo paso recomendado

Validar stack Docker completo, luego avanzar a Tarea #3: CI con GitHub Actions (lint + type-check + tests).

---

## Sesión 4 — 2026-05-10

**Rama:** `chore/diagnostico-inicial`
**Agente:** Claude (Anthropic)
**Objetivo declarado:** Tarea #3 — CI con GitHub Actions + corrección de migraciones pendientes.

### Tareas completadas

1. **`.github/workflows/ci.yml` creado** (commit `f980fd6`):
   - Job `backend`: ubuntu-latest + servicio PostgreSQL 17-alpine, instala deps, `django check`, `pytest tests_api/`.
   - Job `frontend`: ubuntu-latest, `npm ci`, `tsc --noEmit`, `npm run lint` (continue-on-error: 31 errores preexistentes).
   - Concurrency group cancela runs anteriores del mismo branch.

2. **CI falló en primera ejecución**: `relation "inventario_unidad_medida" does not exist`.
   - Causa: 7 apps del codebase heredado tenían cambios de modelo sin migraciones generadas.
   - pytest-django crea la DB desde las migraciones → las tablas se creaban con nombres viejos → `serialize_db_to_string()` fallaba al leer el nombre nuevo definido en `Meta.db_table`.

3. **`makemigrations` ejecutado** — 7 archivos generados:
   - `core/0007`: alter field es_superusuario_omni
   - `compras/0003`: rename ordencompra → compras_orden_compra, alter unique_together
   - `cuentas_por_pagar/0002`: delete model PagoCxP
   - `fiscal/0002`: delete model PagoContribucionParafiscal
   - `inventario/0002`: rename unidadmedida → inventario_unidad_medida, rename producto → inventario_producto, alter unique_together + índices
   - `nomina/0002`: alter unique_together en 3 modelos
   - `ventas/0008`: delete PagoPedido, rename 4 tablas, añade índices

4. **`migrate` aplicado** localmente — OK.

5. **Tests: 6/6 PASSED** localmente.

6. **Commit `b98adb3` pusheado** — CI en ejecución.

### Decisiones tomadas

- Se generaron las migraciones del codebase heredado sin modificar los modelos (solo `makemigrations`).
- No se aplicó migración `core/0006_rename_es_superusuario_innova_to_omni` manual — ya estaba en la DB del usuario desde sesión anterior; la nueva `0007` la continúa correctamente.

### Resultado esperado

CI backend job: GREEN. Frontend job: GREEN (tsc) + continue-on-error (ESLint).

### Próximo paso recomendado

Tarea #4: Refactor con TanStack Query — instalar `@tanstack/react-query` v5, migrar 3-5 páginas críticas.

---

## Sesión 5 — 2026-05-10

**Rama:** `chore/diagnostico-inicial`
**Agente:** Claude (Anthropic)
**Objetivo declarado:** Documentar decisiones arquitectónicas offline-first. Sin código de producto.

### Tareas completadas

1. **PARTE 0 — Arranque:** repo limpio, CI verde, `docs/decisions/` vacío (solo `.gitkeep`).

2. **ADR-001 creado** (`docs/decisions/ADR-001-postgres-server-offline-clients.md`):
   - Postgres en servidor + offline-first en 3 niveles en clientes.
   - Alternativas A-D documentadas y razones de rechazo.
   - Cronograma por nivel: Nivel 1 desde Fase 0, Nivel 2 por módulo, Nivel 3 solo con cliente concreto.

3. **README de decisions creado** (`docs/decisions/README.md`):
   - Índice de ADRs con criterios de creación y proceso de revisión.

4. **Cambio 1** — `02_PLAN_EJECUCION_FOUNDER_SOLO.md` sección 1.2:
   - "cinco" → "seis" propiedades irrenunciables.
   - Propiedad #6: Resiliencia ante conectividad inestable.

5. **Cambio 2** — `OMNI_AI_NATIVE_EXECUTION_PLAN.md` Apéndice A (v1):
   - A-021 agregado: Postgres servidor + offline-first 3 niveles.
   - El Apéndice A de v2.0 solo tiene puntero a v1 (sin tabla propia) → fallback aplicado.

6. **Cambio 3 (Opción B)** — `02_PLAN_EJECUCION_FOUNDER_SOLO.md` PARTE II:
   - R-CODE-2 expandida directamente en v2.0 (el texto original estaba solo en v1).
   - Sección "Reglas con texto expandido en v2.0" creada como contenedor.
   - Excepción explícita: SQLite-as-local-storage en cliente (móvil nativo) es aceptable.

7. **Cambio 4** — `01_MVP_SCOPE_NEGOCIOS_PILOTO.md` sección 5.1:
   - Tabla 5 filas → 6 filas con kiosco autoservicio como capacidad #2.
   - Bloque explicativo: perfiles POS (mostrador vs kiosco cliente), justificación, cuándo.

8. **Cambio 5** — `02_PLAN_EJECUCION_FOUNDER_SOLO.md` sección 5.7:
   - Tabla de hitos del año 1 actualizada: Service Workers en mes 1, POS Nivel 2 en mes 7, kiosco+vendedores en mes 8-9.

9. **Cambio 6** — `02_PLAN_EJECUCION_FOUNDER_SOLO.md` Apéndice C.1:
   - Idea #8: plataforma crédito al consumidor (modelo Cashea) con advertencias explícitas.

10. **Commit `264c701` y push.** CI verde (solo docs, no hay tests afectados).

### Decisiones tomadas

- Cambio 3: Opción B (insertar R-CODE-2 expandida en v2.0 directamente). El texto original solo existía en v1.
- No se creó un PR nuevo; el commit se incorporó al PR existente (#1, `chore/diagnostico-inicial`).
- Placeholders `[Fecha de aplicación]` y `[Fecha]` reemplazados con `2026-05-10`.

### Checks post-aplicación

- [x] ADR-001 existe en `docs/decisions/`
- [x] README de decisions referencia ADR-001
- [x] Plan v2.0 sección 1.2 menciona 6 propiedades
- [x] R-CODE-2 menciona excepción de cliente local
- [x] MVP scope sección 5.1 tiene 6 capacidades
- [x] Kiosco autoservicio documentado con justificación
- [x] Tabla de hitos incluye offline-first (mes 1, 7, 8-9)
- [x] Apéndice C tiene idea Cashea con advertencia

### Próximo paso recomendado

Retomar orden de tareas del Sub-fase 1.A: Tarea #5 (División de ModalPago.tsx).

---

## Sesión 6 — 2026-05-11

**Rama:** `chore/diagnostico-inicial`
**Agente:** Claude (Anthropic)
**Objetivo declarado:** Tareas #6, #7 y #8 de Sub-fase 1.A.

### Tarea #6 completada — Eliminar todos los tipos `any` de TypeScript

1. **31 errores ESLint eliminados** en 11 archivos:
   - `no-explicit-any` ×21: interfaces tipadas en `CotizacionDetailPage.tsx`, `FacturaFiscalDetailPage.tsx`, `MonedaDetailPage.tsx`, `MonedaFormPage.tsx`, `FormularioProducto.tsx`
   - `no-unused-vars` ×3: renombrado `idDocumento → _idDocumento` (ModalPago), removidos imports sin uso (useCotizacionForm)
   - `react-refresh/only-export-components` ×4: `eslint-disable` con comentario justificativo en `SidebarContext.tsx`, `AuthContext.tsx`, `coreRoutes.tsx`
2. **`eslint.config.js`**: regla `argsIgnorePattern: '^_'` añadida para parámetros stub.
3. **`ci.yml`**: removido `continue-on-error: true` del paso ESLint — ahora bloquea merges.
4. **Resultado**: `tsc --noEmit` CLEAN, `npm run lint` 0 errores.

### Tarea #7 completada — Aislamiento multi-tenant en todos los módulos

1. **6 módulos corregidos** (R-CODE-1 faltaba en `get_queryset`):
   - `inventario/views.py`: 8 viewsets corregidos
   - `compras/views.py`: 3 viewsets corregidos
   - `proveedores/views.py`: `ProveedorViewSet` corregido
   - `gastos/views.py`: 3 viewsets + acción `activas` corregidas
   - `nomina/views.py`: 2 viewsets + acción `activos` corregida
   - `finanzas/views.py`: `PagoViewSet.get_queryset()` añadido
2. **4 URLs wired** en `config/urls.py`: `proveedores`, `gastos`, `nomina`, `cuentas-por-pagar`.
3. **`tests_api/test_aislamiento_multimodulo.py`** creado: 7 clases × 3 tests = 21 tests.
4. **27/27 PASSED** (21 nuevos + 6 originales).

### Tarea #8 completada — Celery + Redis setup

1. **`requirements.txt`**: `celery==5.6.3`, `redis==7.4.0`, `django-celery-beat==2.9.0`, `django-celery-results==2.6.0`.
2. **`config/celery.py`**: instancia Celery `omni_erp`, auto-discovery, `debug_task`.
3. **`config/__init__.py`**: importa `celery_app` para carga temprana.
4. **`settings_base.py`**: bloque `CELERY_*` completo (broker, result backend django-db, timezone, retries, soft/hard time limits, beat scheduler).
5. **`django-celery-beat` y `django-celery-results`** añadidos a `INSTALLED_APPS`.
6. **Migraciones aplicadas**: 19 migraciones de `django_celery_beat` + 14 de `django_celery_results`.
7. **`apps/core/tasks.py`**: tareas `core.ping` y `core.log_evento`.
8. **`apps/auditoria/tasks.py`**: tarea real `auditoria.registrar_evento` (fire-and-forget con acks_late y reintentos).
9. **`docker-compose.yml`**: servicios `celery_worker` (concurrency=2, queues celery+auditoria) y `celery_beat` (DatabaseScheduler).
10. **`.env.example`**: documentado `REDIS_URL` para dev local y Docker.
11. **`tests_api/test_celery_tasks.py`**: 13 tests con `CELERY_TASK_ALWAYS_EAGER=True`.
12. **`ci.yml`**: `REDIS_URL` añadido al env (satisface settings; no necesita broker real porque los tests usan ALWAYS_EAGER).
13. **40/40 PASSED**.

### Decisiones tomadas

- `django-celery-results` como result backend (en vez de Redis) para persistir resultados en PostgreSQL — más simple para inspección y auditoría en dev.
- `acks_late=True` en `registrar_evento` para garantizar at-least-once delivery.
- `max_retries=0` en `core.ping` — no tiene sentido reintentar un health-check.
- No se crea `celery_beat` con `schedule.ini` — se usa `DatabaseScheduler` para que el schedule sea administrable desde Django Admin sin redeploy.
- Tests usan `CELERY_TASK_ALWAYS_EAGER=True` y `CELERY_TASK_EAGER_PROPAGATES=True` — no requieren Redis en CI.

### Próximo paso recomendado

Tarea #9: MinIO / S3-compatible para archivos (o según el orden aprobado de Sub-fase 1.A).

---
