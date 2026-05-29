# App `agentes`

Capa de agentes IA del sistema (AI-nativo). Configura agentes por capacidad, registra sus predicciones/sugerencias y expone endpoints para invocar análisis (cobranza, reorden de inventario, personalización, clasificación de gastos) con autonomía graduada (ver `NivelAutonomia` y [ADR-004](../../../docs/decisions/ADR-004-agent-stack-anthropic-sdk.md)).

**Prefijo API:** `/api/agentes/`

## Modelos

| Modelo | Descripción |
|---|---|
| `ConfigAgente` | Configuración de un agente (capacidad, nivel de autonomía). |
| `PrediccionAgente` | Predicción/sugerencia generada por un agente. |
| `NivelAutonomia` | Enum de niveles de autonomía (sugerir → ejecutar con supervisión). |

## Endpoints

Recurso REST (CRUD vía router): `predicciones/`.

| Ruta | Descripción |
|---|---|
| `POST chat/` | Chat con el asistente IA (`AsistenteChatView`). |
| `POST predicciones/analizar-cobranza/` | Análisis de cobranza por IA. |
| `POST predicciones/analizar-reorden/` | Sugerencias de reorden de inventario. |
| `POST predicciones/analizar-personalizacion/` | Análisis de personalización. |
| `POST predicciones/clasificar-gasto/` | Clasificación automática de gastos. |
| `GET predicciones/metricas-clasificador/` | Métricas del clasificador de gastos. |
| `GET predicciones/sugerencias-activas/` | Sugerencias activas pendientes. |
| `POST predicciones/{id}/responder/` | Responder/actuar sobre una sugerencia. |
| `PATCH predicciones/{id}/evaluar/` | Evaluar (feedback) una predicción. |
