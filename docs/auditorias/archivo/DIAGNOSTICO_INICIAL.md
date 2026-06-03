# Diagnóstico Inicial — Omni ERP

**Fecha:** 2026-05-10
**Sesión:** 1 (`chore/diagnostico-inicial`)
**Agente:** Claude (Anthropic)
**Rama inspeccionada:** `main` (commit `dbaf8a4`)
**Propósito:** Relevar el estado real del repositorio unificado antes de iniciar Sub-fase 1.A.

---

## 1. Estado de la Build

### 1.1 Backend (Django)

| Verificación | Resultado | Detalle |
|---|---|---|
| `python manage.py check` | **ROJO → VERDE** | Falla sin intervención: `ModuleNotFoundError: No module named 'django_filters'`. Tras instalar `django-filter==24.3` manualmente: 0 issues. |
| `python manage.py showmigrations` | **AMARILLO** | 1 migración pendiente: `manufactura 0002_fix_codigo_unique_per_empresa [ ]` |
| `python manage.py makemigrations --check` | **VERDE** | No hay modelos sin migrar. |
| Tests (`pytest`) | **ROJO** | `ImportError: cannot import name 'Moneda' from 'apps.core.models'` en `conftest.py`. El modelo está en `apps.finanzas.models`. 0 tests pasan. |

**Conclusión backend:** El proyecto no arranca sin instalar manualmente un paquete que está en `requirements.txt`. Esto indica que el venv está desincronizado con el archivo de dependencias. Además, el único archivo de tests tiene un import roto que bloquea toda la suite.

### 1.2 Frontend (React/TypeScript)

| Verificación | Resultado | Detalle |
|---|---|---|
| `tsc --noEmit` | **VERDE** | 0 errores de tipado. |
| ESLint (`npm run lint`) | **ROJO** | 31 errores, 1 advertencia. |

**Errores ESLint detallados:**

| Archivo | Cantidad | Tipo |
|---|---|---|
| `FacturaFiscalDetailPage.tsx` | 7 | `@typescript-eslint/no-explicit-any` |
| `coreRoutes.tsx` | 2 | `react-refresh/only-export-components` |
| `pagosService.ts` | 1 | `@typescript-eslint/no-unused-vars` (`_vueltos`) |
| Otros (estimado) | ~21 | `no-explicit-any` disperso |

**Conclusión frontend:** TypeScript compila limpio, pero el linter detecta 31 violaciones, principalmente tipos `any` explícitos. La regla R-CODE-3 ("sin `any`") del plan de ejecución ya está violada en código heredado.

---

## 2. Estructura del Código

### 2.1 Django Apps (Backend)

Conteo global: **263 archivos Python**, **29 apps Django**.

| App | Estado | Descripción | Modelos principales |
|---|---|---|---|
| `core` | Funcional | Multi-tenant base, auth, empresas, usuarios, dispositivos, cajas | `Empresa`, `Usuarios`, `Dispositivo`, `SesionCaja` |
| `finanzas` | Funcional | Facturas, pagos, monedas, tasas, CxC | `Factura`, `Pago`, `Moneda`, `TasaCambio`, `CuentaPorCobrar` |
| `ventas` | Funcional | Clientes, pedidos, productos básicos | `Cliente`, `Pedido`, `ProductoVenta` |
| `fiscal` | Funcional (sin modelos propios) | Serializers y views para reportes SENIAT; usa modelos de `finanzas` | — |
| `configuracion_motor` | Funcional | Motor de configuración dinámica | `ConfiguracionMotor`, `ValorConfiguracion` |
| `auditoria` | Funcional | Log de eventos de auditoría | `EventoAuditoria` |
| `inventario` | Parcial | Modelos básicos, sin movimientos completos | `Producto`, `Stock` |
| `compras` | Parcial | Estructura sin lógica completa | `OrdenCompra`, `ProveedorCompra` |
| `cxc` | Parcial | Duplica funcionalidad con `finanzas.CuentaPorCobrar` | `CuentaCxC` |
| `cxp` | Parcial | Solo estructura inicial | `CuentaPorPagar` |
| `manufactura` | Parcial | BOM y órdenes de fabricación básicas | `OrdenFabricacion`, `BOM`, `ItemBOM` |
| `rrhh` | Solo estructura | Models vacíos / stubs | — |
| `nomina` | Solo estructura | Models vacíos / stubs | — |
| `almacenes` | Solo estructura | Models vacíos / stubs | — |
| `crm` | Solo estructura | Models vacíos / stubs | — |
| `tesoreria` | Solo estructura | Models vacíos / stubs | — |
| `gestion_documental` | Solo estructura | Models vacíos / stubs | — |
| `saas_core` | No existe | Gestión SaaS, billing, onboarding | — |
| `notificaciones` | No existe | Push, email, in-app, Telegram | — |
| `retail_pos` | No existe | POS táctil para distribuidora | — |
| `portal_cliente` | No existe | Portal self-service clientes | — |
| `portal_proveedor` | No existe | Portal self-service proveedores | — |
| `delivery_general` | No existe | Gestión de entregas | — |
| `ml_ops` | No existe | Plano agéntico, evaluaciones | — |
| `mcp_runtime` | No existe | MCP runtime per módulo | — |
| `event_store` | No existe | Event sourcing, Redpanda | — |
| `i18n_ve` | No existe | Localización venezolana | — |

### 2.2 Frontend (React/TypeScript)

Conteo global: **139 archivos TypeScript** (41 `.ts` + 98 `.tsx`).

| Sección | Páginas/Componentes | Estado estimado |
|---|---|---|
| Auth (login, sesión caja) | ~4 páginas | Funcional |
| Dashboard | ~2 páginas | Funcional |
| Ventas (pedidos, clientes, facturación) | ~15 páginas | Funcional |
| Finanzas (pagos, monedas, tasas) | ~8 páginas | Funcional |
| Fiscal (facturas fiscales, libros) | ~5 páginas | Funcional |
| Inventario | ~4 páginas | Parcial |
| Manufactura | ~3 páginas | Parcial |
| Configuración | ~3 páginas | Funcional |
| CxC | ~3 páginas | Parcial |
| Compras | ~2 páginas | Parcial |

**Componente problemático:** `ModalPago.tsx` — **1091 líneas** en un único componente. El Master Plan (sección 2.4) lo reportaba como `~600 líneas`; la realidad es 82% más grande.

**Hooks:** `useDocumentoVentaBase.ts` existe como intento de extracción, pero los 4 hooks específicos (`useFacturaVenta`, `usePedidoVenta`, `useCreditoVenta`, `useDevolucionVenta`) siguen existiendo por separado, indicando que la refactorización está incompleta.

**Gestión de estado:** 0 instancias de `@tanstack/react-query`. 178 llamadas a `useEffect` en 73 archivos — toda la lógica de fetching es manual con `axios` + `useEffect` + `useState`.

---

## 3. Estado de la Deuda Técnica Heredada

### 3.1 Deudas declaradas como "corregidas" en Master Plan 2.3

El Master Plan lista 19 bugs corregidos en la auditoría de abril 2026. Se verificaron los siguientes:

| # | Deuda declarada corregida | Verificación | Resultado |
|---|---|---|---|
| 1 | `console.log` eliminados | `grep -r "console\.log"` en frontend/src | **FALSO** — 85 ocurrencias en 38 archivos. |
| 2 | Tipos `any` eliminados | ESLint `no-explicit-any` | **FALSO** — 7+ en FacturaFiscalDetailPage.tsx, más en otros. |
| 3 | `ModalPago.tsx` refactorizado | Contar líneas | **FALSO** — 1091 líneas (Master Plan decía ~600). |
| 4 | `useDocumentoVentaBase` centraliza hooks | Verificar hooks hijos | **PARCIAL** — El hook base existe pero los 4 hijos no fueron eliminados. |
| 5 | Migración `0006_rename_es_superusuario` | Verificar archivo | **VERDADERO** — Migración creada correctamente en esta sesión. |
| 6 | Todos los imports organizados | No verificado exhaustivamente | **DESCONOCIDO** |

**Conclusión:** Al menos 3 de las 19 correcciones declaradas no están aplicadas en el código. El Master Plan refleja estado deseado, no estado real.

### 3.2 Deudas pendientes declaradas en Master Plan 2.4

| # | Deuda | Estado real verificado |
|---|---|---|
| D-001 | SQLite en dev | **CONFIRMADO** — `settings_base.py` líneas 106-107 aún tiene SQLite como fallback. `.env` tiene `DB_HOST=` vacío. |
| D-002 | Sin TanStack Query | **CONFIRMADO** — No está en `package.json`. 178 `useEffect`. |
| D-003 | Tipos `any` en frontend | **CONFIRMADO** — 31 errores ESLint incluyendo `any`. |
| D-004 | 0% cobertura de tests | **CONFIRMADO** — 0 tests en `backend/apps/`, 0 en `frontend/src/`. `conftest.py` con import roto. |
| D-005 | `ModalPago.tsx` demasiado grande | **CONFIRMADO** — 1091 líneas. |
| D-006 | Sin Celery | **CONFIRMADO** — `celery` no está en venv ni en requirements.txt (falta añadir). |
| D-007 | Sin Redis | **CONFIRMADO** — No está instalado. |
| D-008 | Hooks duplicados | **CONFIRMADO** — Hook base + 4 hijos siguen coexistiendo. |

**Todas las 8 deudas pendientes declaradas están confirmadas como reales.**

### 3.3 Deudas adicionales encontradas (no documentadas en Master Plan)

| # | Deuda nueva | Criticidad |
|---|---|---|
| D-009 | `django-filter` en requirements.txt pero no instalado en venv | ALTA — bloquea arranque |
| D-010 | `tests_api/conftest.py` con import roto (`Moneda` from `core.models`) | ALTA — 0 tests pueden correr |
| D-011 | Migración pendiente: `manufactura/0002_fix_codigo_unique_per_empresa` | MEDIA — riesgo de inconsistencia en producción |
| D-012 | `console.log/warn/error`: 85 ocurrencias en 38 archivos | MEDIA — información sensible podría exponerse en producción |
| D-013 | `FacturaFiscalDetailPage.tsx` usa 7 `any` explícitos | MEDIA — viola R-CODE-3 |
| D-014 | `pagosService.ts` tiene variable `_vueltos` sin usar | BAJA |
| D-015 | Finanzas tiene migraciones 0021/0022/0023 que no aparecen en `showmigrations` output estándar | MEDIA — investigar si están aplicadas |

---

## 4. Cobertura de Tests Actual

### 4.1 Backend

| Ubicación | Tests encontrados | Estado |
|---|---|---|
| `backend/apps/*/tests.py` | 0 archivos con tests | — |
| `backend/tests_api/` | 1 `conftest.py` con import roto | No corren |
| Cobertura estimada | **0%** | — |

El import roto en `conftest.py`:
```python
from apps.core.models import Moneda  # Moneda está en apps.finanzas.models
```
Este error bloquea la colección de pytest para todo el proyecto.

### 4.2 Frontend

| Ubicación | Tests encontrados | Estado |
|---|---|---|
| `frontend/src/**/*.test.*` | 0 archivos | — |
| `frontend/src/**/*.spec.*` | 0 archivos | — |
| Cobertura estimada | **0%** | — |

**Conclusión:** El proyecto está en estado pre-testing. Ningún comportamiento crítico está protegido por tests automatizados. Cualquier refactorización o extensión conlleva riesgo elevado de regresión no detectada.

---

## 5. Dependencias Instaladas vs. Requeridas para Fase 0

### 5.1 Backend — Gap analysis

| Paquete | En requirements.txt | En venv (.venv) | Requerido para Fase 0 | Acción |
|---|---|---|---|---|
| `django==5.2.4` | Sí | Sí | Sí | OK |
| `djangorestframework` | Sí | Sí | Sí | OK |
| `django-filter==24.3` | Sí | **NO** | Sí | Instalar + verificar |
| `psycopg2-binary` | Sí | Verificar | Sí (PostgreSQL) | Instalar si falta |
| `celery` | **NO** | No | Sí | Agregar a requirements + instalar |
| `redis` | **NO** | No | Sí | Agregar a requirements + instalar |
| `anthropic` (SDK) | No | No | Sí (AI primitives) | Agregar + instalar |
| `mcp` (SDK Python) | No | No | Sí (MCP runtime) | Agregar + instalar |
| `uuid7` | No | No | Sí (R-CODE-5: UUIDv7) | Agregar + instalar |
| `redpanda-client` o `kafka-python` | No | No | Sí (event sourcing) | Agregar + instalar |
| `pytest-django` | En req | Verificar | Sí (tests) | Verificar |
| `factory-boy` | En req | Verificar | Sí (tests) | Verificar |
| `python-decouple` | En req | Sí | Sí | OK |
| `gunicorn` | En req | Verificar | Prod only | OK para más adelante |

### 5.2 Frontend — Gap analysis

| Paquete | En package.json | Requerido para Fase 0 | Acción |
|---|---|---|---|
| `react==19.x` | Sí | Sí | OK |
| `@mui/material==7.x` | Sí | Sí | OK |
| `axios` | Sí | Sí | OK |
| `react-router-dom` | Sí | Sí | OK |
| `@tanstack/react-query` | **NO** | Sí (D-002) | Instalar (v5) |
| `i18next` | **NO** | Sí (localización i18n_ve) | Instalar |
| `react-i18next` | **NO** | Sí | Instalar |
| `zod` | **NO** | Recomendado (validación) | Evaluar |
| `vitest` | **NO** | Sí (tests) | Instalar |
| `@testing-library/react` | **NO** | Sí (tests) | Instalar |

---

## 6. Brechas vs. Visión AI-Nativa

Las 8 primitivas AI-nativas del plan de ejecución (`OMNI_AI_NATIVE_EXECUTION_PLAN.md`) se contrastan con el estado actual:

### 6.1 Event Sourcing (Redpanda)

**Estado actual:** No existe ningún componente de event sourcing. No hay `EventStore`, no hay `DomainEvent`, no hay consumidores Redpanda, no hay Celery para procesamiento asíncrono. Toda la lógica es request/response síncrono.

**Brecha:** 100%. Punto de partida en cero.

**Impacto:** Sin event sourcing, no hay audit trail inmutable, no hay capacidad de replay, no hay base para agentes reactivos a eventos de negocio.

### 6.2 MCP Runtime por Módulo

**Estado actual:** No existe ninguna infraestructura MCP. No hay `mcp_runtime` app, no hay decoradores `@register_capability`, no hay servidor MCP configurado. La skill `omni-venezuela-fiscal` y otras skills asumen esta infraestructura operativa.

**Brecha:** 100%. El SDK Python de MCP ni siquiera está instalado.

**Impacto:** Sin MCP runtime, ningún módulo puede ser consumido por agentes IA de forma estructurada. La integración con Claude debe hacerse via REST crudo (frágil, no tipado, sin control de capacidades).

### 6.3 Plano Agéntico (Orquestación Multi-Agente)

**Estado actual:** No existe. No hay `AgentRegistry`, no hay `AgentTask`, no hay cola de tareas agénticas, no hay routing de intenciones.

**Brecha:** 100%.

**Impacto:** Los 2 agentes del MVP (cobranza assistant + stock assistant) no tienen infraestructura donde correr.

### 6.4 DSL de Personalización

**Estado actual:** El `configuracion_motor` app existe y tiene estructura para configuraciones clave-valor. Sin embargo, no hay DSL declarativo YAML/JSON para customizaciones de negocio. Las customizaciones actuales son hardcoded o via admin de Django.

**Brecha:** 95%. La base de configuración existe pero no como DSL versionable.

**Impacto:** Cada customización de cliente requiere código Python nuevo. No hay personalización sin programación.

### 6.5 Sandbox de Evaluación (Eval Suite)

**Estado actual:** No existe. No hay framework de evaluación de agentes, no hay datasets de prueba para escenarios venezolanos, no hay métricas de calidad agéntica.

**Brecha:** 100%.

**Impacto:** No hay forma de medir si los agentes mejoran o empeoran entre versiones. Las regresiones agénticas son indetectables.

### 6.6 Multi-LLM (Claude default + GPT + Gemini + local)

**Estado actual:** Ningún LLM está integrado. El SDK de Anthropic no está instalado. No hay abstracción de LLM provider.

**Brecha:** 100%.

**Impacto:** No hay ninguna capacidad IA funcionando hoy.

### 6.7 Localización Venezolana (i18n_ve)

**Estado actual:** No existe el paquete. Las cadenas están en español de Argentina/España mezclado (montos, fechas, terminología fiscal). No hay `i18next` en el frontend ni `gettext` en el backend.

**Brecha:** 90%. Hay texto en español pero no localización formal ni terminología venezolana estandarizada.

**Impacto:** Confusión terminológica con el cliente piloto venezolano. Formateo de fechas y montos no estándar para Venezuela.

### 6.8 Primitiva de Contexto Empresa (Context Propagation)

**Estado actual:** El contexto de empresa se propaga via `request.user.empresa` en viewsets. No hay context propagation para Celery tasks (deben recibir `empresa_id` manualmente). No hay context propagation para agentes IA.

**Brecha:** 40%. El patrón existe para HTTP; falta para background tasks y agentes.

**Impacto:** Riesgo de leak de contexto multi-tenant en tasks asíncronas y en llamadas agénticas.

### Resumen de brechas

| Primitiva | Brecha | Prioridad Sub-fase 1.A |
|---|---|---|
| Event Sourcing (Redpanda) | 100% | Mes 2-3 (Fase 0.C) |
| MCP Runtime | 100% | Mes 1 (Fase 0.A) — prioritario |
| Plano Agéntico | 100% | Mes 2-3 (Fase 0.C) |
| DSL Personalización | 95% | Mes 3-4 (Fase 0.D) |
| Eval Suite | 100% | Mes 2 (Fase 0.B) |
| Multi-LLM | 100% | Mes 1 (Fase 0.A) — SDK primero |
| Localización Venezolana | 90% | Mes 2 (Fase 0.B) |
| Context Propagation | 40% | Mes 1 (Fase 0.A) — completar |

---

## 7. Riesgos Detectados

### R-001 — Build roto sin intervención manual [CRÍTICO]

**Descripción:** `django-filter` está en `requirements.txt` pero no en el venv. El proyecto no arranca sin `pip install django-filter==24.3` manual.

**Impacto:** Cualquier nuevo desarrollador o CI pipeline falla en el primer intento.

**Mitigación recomendada:** Correr `pip install -r requirements.txt` completo y verificar que el venv esté sincronizado. Agregar step de verificación en CI.

### R-002 — Tests con import roto [CRÍTICO]

**Descripción:** `tests_api/conftest.py` importa `Moneda` desde `apps.core.models` cuando está en `apps.finanzas.models`. pytest falla en colección.

**Impacto:** 0 tests pueden correr. No hay red de seguridad para ningún cambio.

**Mitigación recomendada:** Corregir import. Ejecutar suite completa. Agregar al menos 3 tests de aislamiento multi-tenant como base.

### R-003 — Migración pendiente en producción [ALTA]

**Descripción:** `manufactura/0002_fix_codigo_unique_per_empresa` está sin aplicar. Si hay datos en manufactura, la migración podría fallar por violaciones de unicidad.

**Impacto:** Si se corre `migrate` en producción sin revisar datos, podría haber error de integridad.

**Mitigación recomendada:** Revisar si hay datos en la tabla afectada antes de migrar. Correr `migrate` en staging primero.

### R-004 — console.log en código de producción [MEDIA]

**Descripción:** 85 ocurrencias de `console.log/warn/error` en 38 archivos del frontend. El Master Plan declaraba que estaban eliminados.

**Impacto:** Información de negocio (montos, RIF, datos de clientes) puede aparecer en la consola del browser de usuarios finales. Riesgo de privacidad.

**Mitigación recomendada:** Eliminar todos los `console.*` excepto los que están en bloques `catch` (mantener como `console.error` solo en dev). Usar un logger configurable.

### R-005 — Solapamiento CxC [MEDIA]

**Descripción:** El módulo `finanzas` tiene `CuentaPorCobrar` y el módulo `cxc` tiene `CuentaCxC`. Son conceptualmente equivalentes.

**Impacto:** Confusión de cuál usar. Riesgo de que datos queden en uno y no en el otro. Duplicación de lógica de cobranza.

**Mitigación recomendada:** Decidir en Sub-fase 1.A cuál es canónico. Migrar datos y deprecar el otro. Documentar como decisión técnica.

### R-006 — SQLite como fallback silencioso [MEDIA]

**Descripción:** `settings_base.py` tiene SQLite como fallback cuando `DB_HOST` está vacío. En dev local, la app corre sobre SQLite sin warning explícito.

**Impacto:** Diferencias de comportamiento entre dev (SQLite) y prod (PostgreSQL). Consultas que funcionan en SQLite pueden fallar en Postgres.

**Mitigación recomendada:** Eliminar fallback a SQLite. Forzar error explícito si `DB_HOST` no está configurado. Proveer `docker-compose.yml` con Postgres para dev.

### R-007 — Deuda fiscal sin tests [ALTA]

**Descripción:** Todo el módulo fiscal (IVA 16%, IGTF 3%, retenciones 75%/100%, libros SENIAT) tiene 0% de cobertura. La skill `omni-venezuela-fiscal` exige que estos cálculos sean deterministas y nunca delegados a LLM.

**Impacto:** Cualquier cambio en lógica fiscal puede introducir errores que el SENIAT penaliza.

**Mitigación recomendada:** Priorizar tests unitarios de todos los cálculos fiscales antes de conectar a piloto real.

---

## 8. Recomendación de Orden de Trabajo — Sub-fase 1.A (Mes 1)

Basado en el diagnóstico, propongo el siguiente orden de trabajo para las primeras 4 semanas:

### Semana 1 — Reparar el piso (Pre-requisitos bloqueantes)

**Objetivo:** Llegar a un estado donde el build es 100% reproducible y los tests pueden correr.

1. Sincronizar venv: `pip install -r requirements.txt` completo. Verificar todos los paquetes.
2. Corregir import en `tests_api/conftest.py` (`Moneda` → `apps.finanzas.models`).
3. Aplicar migración pendiente: `python manage.py migrate manufactura`.
4. Configurar PostgreSQL local via Docker Compose. Eliminar fallback SQLite.
5. Correr `python manage.py migrate` completo sobre Postgres. Verificar 0 errores.
6. Escribir 3 tests de aislamiento multi-tenant mínimos (empresa A no ve datos empresa B).

**Entregable:** Build verde reproducible + CI capaz de correr tests.

### Semana 2 — Limpiar deuda de código

**Objetivo:** Llevar el código al estado que el Master Plan decía que ya estaba.

1. Eliminar todos los `console.log/warn/error` innecesarios (85 ocurrencias).
2. Eliminar tipos `any` explícitos en frontend (31 errores ESLint → 0).
3. Instalar `@tanstack/react-query` v5. Migrar 3-5 páginas críticas como piloto.
4. Extraer `ModalPago.tsx` en componentes menores (objetivo: <400 líneas por componente).
5. Resolver solapamiento `finanzas.CuentaPorCobrar` vs `cxc.CuentaCxC`.

**Entregable:** ESLint verde. TanStack Query instalado y probado en páginas piloto.

### Semana 3 — Instalar dependencias Fase 0

**Objetivo:** Tener el stack de Fase 0 instalado y verificado, aunque no usados aún.

1. Agregar a requirements: `celery`, `redis`, `anthropic`, `uuid7`, `mcp` SDK.
2. Instalar y verificar que Django arranca con todos instalados.
3. Agregar a package.json: `@tanstack/react-query`, `i18next`, `react-i18next`, `vitest`, `@testing-library/react`.
4. Configurar Celery con Redis como broker (solo configuración, sin tasks).
5. Primera prueba de conexión con Anthropic API (hello world, no lógica de negocio).

**Entregable:** Stack Fase 0 instalado. `manage.py check` verde con todos los paquetes.

### Semana 4 — Primitiva MCP v0

**Objetivo:** Crear el `mcp_runtime` app con la infraestructura mínima para exponer capacidades.

1. Crear app `mcp_runtime` con estructura según `omni-django-module` skill.
2. Implementar decorador `@register_capability` básico.
3. Exponer 1 capacidad de prueba del módulo `finanzas` (ej: `consultar_cuentas_vencidas`).
4. Test de aislamiento: la capacidad solo devuelve datos de la empresa del token.
5. Documentar capacidad en formato MCP.

**Entregable:** Primer endpoint MCP funcional con aislamiento verificado.

---

## 9. Observaciones Cualitativas

### 9.1 El código heredado es de buena factura, pero incompleto

La arquitectura base (multi-tenant con `id_empresa`, `BaseModelViewSet`, serializers tipados, separación de apps) refleja criterio técnico sólido. No es código de prototipo descartable — es una base que vale la pena extender.

El problema no es calidad del código existente sino **honestidad de documentación**: el Master Plan describía un estado más avanzado del que existe realmente. Esto es riesgo porque puede llevar a decisiones basadas en capacidades que no están implementadas.

### 9.2 La brecha AI-nativa es de infraestructura, no de arquitectura

El diseño de Omni como sistema AI-nativo está bien pensado en los documentos. La arquitectura (event sourcing, MCP runtime, plano agéntico, DSL) es coherente y tiene precedentes sólidos en la industria.

La brecha es de implementación: ninguna de las 8 primitivas AI-nativas existe en código. El trabajo de Sub-fase 1.A es convertir esos documentos en infraestructura real, pieza por pieza.

### 9.3 El módulo fiscal es el más crítico y el más frágil

`apps.fiscal` implementa lógica SENIAT (IVA, IGTF, retenciones, libros) que tiene consecuencias legales reales. Es el módulo que más valor aporta en el contexto venezolano y el que tiene 0% de tests.

Antes de conectar cualquier cliente piloto real, este módulo debe tener cobertura de tests exhaustiva. Ningún cálculo fiscal debe pasar por un LLM — la skill `omni-venezuela-fiscal` es correcta en esto.

### 9.4 La multi-tenancy está bien estructurada pero no verificada

El patrón `BaseModelViewSet` + filtro por `id_empresa` es correcto. Sin embargo, sin tests de aislamiento, no hay garantía de que no haya escapes en servicios, signals o tasks.

La ausencia total de tests significa que la multi-tenancy podría estar rota en puntos no visibles durante la inspección estática del código.

### 9.5 El proyecto está listo para Fase 0

A pesar de las deudas, el proyecto tiene la masa crítica necesaria para comenzar la Fase 0 de forma ordenada:
- Arquitectura Django probada y funcional.
- Frontend React con MUI funcionando.
- Autenticación, multi-tenant y fiscal implementados.
- Skills y protocolo de ejecución definidos.
- Repositorio unificado en GitHub.

Con 2-3 semanas de reparación de piso, el proyecto puede sostener la construcción de primitivas AI-nativas sin riesgo de que la deuda técnica heredada cause problemas.

---

*Diagnóstico producido en Sesión 1 — 2026-05-10*
*Próxima revisión: al finalizar Sub-fase 1.A (Mes 1)*
