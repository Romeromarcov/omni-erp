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
