# App `agentes`

Capa de agentes IA del sistema (AI-nativo). Configura agentes por capacidad, registra sus predicciones/sugerencias y ejecuta análisis asíncronos fuera del request HTTP mediante Celery (`EjecucionAgente`) con autonomía graduada (ver `NivelAutonomia` y [ADR-004](../../../docs/decisions/ADR-004-agent-stack-anthropic-sdk.md)).

**Prefijo API:** `/api/agentes/`

## Modelos

| Modelo | Descripción |
|---|---|
| `ConfigAgente` | Configuración de un agente (capacidad, nivel de autonomía). |
| `PrediccionAgente` | Predicción/sugerencia generada por un agente. |
| `EjecucionAgente` | Registro de ejecución asíncrona en Celery (`pendiente` → `ejecutando` → `completado` \| `fallido`). |
| `ConsumoLLM` | Registro persistente e inmutable de tokens, latencia y costo estimado USD por llamada al gateway LLM. |
| `NivelAutonomia` | Enum de niveles de autonomía (sugerir → ejecutar con supervisión). |

## Endpoints

Recursos REST (vía router): `predicciones/`, `ejecuciones/` (solo lectura) y `consumo-llm/` (solo lectura).

| Ruta | Descripción |
|---|---|
| `POST chat/` | Chat con el asistente IA (`AsistenteChatView`, streaming SSE). |
| `POST predicciones/analizar-cobranza/` | Encola análisis de cobranza en Celery (`HTTP 202` → `EjecucionAgente`). |
| `POST predicciones/analizar-reorden/` | Encola sugerencias de reorden en Celery (`HTTP 202` → `EjecucionAgente`). |
| `POST predicciones/analizar-personalizacion/` | Encola análisis de personalización en Celery (`HTTP 202` → `EjecucionAgente`). |
| `POST predicciones/clasificar-gasto/` | Encola clasificación de gasto en Celery (`HTTP 202` → `EjecucionAgente`). |
| `GET predicciones/metricas-clasificador/` | Métricas del clasificador de gastos. |
| `GET predicciones/sugerencias-activas/` | Sugerencias activas pendientes. |
| `POST predicciones/{id}/responder/` | Responder/actuar sobre una sugerencia. |
| `PATCH predicciones/{id}/evaluar/` | Evaluar (feedback) una predicción. |
| `GET ejecuciones/` | Lista ejecuciones asíncronas de la empresa (`?agente=`, `?estado=`, `?search=`). |
| `GET ejecuciones/{id}/` | Consulta estado, resultado o error saneado de una ejecución. |
| `GET consumo-llm/` | Lista eventos persistidos de consumo LLM del tenant (`?empresa_id=`, `?modelo=`, `?uso=`, `?fecha_desde=`, `?fecha_hasta=`, `?search=`). |
| `GET consumo-llm/{id}/` | Consulta el detalle de un registro `ConsumoLLM` del tenant. |
| `GET consumo-llm/resumen/` | Resumen agregado (`llamadas`, tokens in/out, `costo_total_usd`, `latencia_promedio_ms`, `por_modelo`, `por_uso`). |

## Tareas Celery y Paridad MCP

- **Celery (`apps/agentes/tasks.py`):**
  - `agentes.ejecutar_analisis_agente`: ejecuta en background el agente solicitado bajo `rls_tenant_context([empresa_id])`.
  - `agentes.generar_sugerencias_diarias`: tarea periódica diaria (Beat).
- **Hook de consumo (`apps/agentes/services.py` + `apps/agentes/apps.py`):**
  - `AgentesConfig.ready()` conecta de forma idempotente `persistir_consumo_llm` a `llm_gateway.registrar_consumo_hook` para registrar tokens y costo USD (`calcular_costo_estimado_usd`) de forma fail-safe.
- **MCP (`apps/agentes/mcp.py`):**
  - `agentes_disparar_analisis` (`agentes:write`)
  - `agentes_obtener_ejecucion` (`agentes:read`)
  - `agentes_listar_ejecuciones` (`agentes:read`)
  - `agentes_resumen_consumo_llm` (`agentes:read`)
