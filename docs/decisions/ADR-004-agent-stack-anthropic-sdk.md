# ADR-004: Stack Agéntico — Anthropic SDK + Orquestación Propia + Shadow Mode

**Estado:** Aceptado
**Fecha:** 2026-05-16
**Autor(es):** Marco Romero, Claude Sonnet 4.6

## Contexto

WS-4 de Fase 0 requiere implementar el primer agente operativo: un clasificador de gastos en shadow mode. Se debe elegir un stack agéntico que sea:
- Compatible con multi-proveedor LLM (A-013)
- No acoplado a frameworks de terceros que cambian rápidamente
- Testeable sin API key real (indispensable para CI)
- Extensible para construir más agentes con el mismo patrón

Se evaluaron: LangChain, CrewAI, AutoGen, LlamaIndex y Anthropic SDK directo.

## Decisión

**Anthropic SDK directo como cliente LLM, con orquestación propia delgada en `apps/agentes/`.**

Cada agente es una clase Python con interfaz `clasificar()` / `ejecutar()` / `sugerir()`. No hay framework de orquestación externo.

El primer agente implementado: `ClasificadorGastos` en shadow mode (predice, no ejecuta).

Patrón de fallback: si no hay `ANTHROPIC_API_KEY` o el LLM falla, el agente cae a un clasificador determinista basado en keywords. Los tests usan inyección de cliente mock.

## Alternativas consideradas

1. **LangChain** — descartada porque: cambia de API cada versión menor; abstracción innecesaria para nuestro caso; bugs de coherencia multi-provider documentados.
2. **CrewAI** — descartada porque: demasiado opinionado en roles/tasks; difícil de depurar; lock-in implícito.
3. **AutoGen** — descartada porque: orientado a multi-agente complejo; overkill para clasificador simple; interfaz de tests poco natural.
4. **LlamaIndex** — descartada porque: foco en RAG/documentos, no en agentes operativos ERP.

## Consecuencias

**Positivas:**
- Tests sin API key real (mock inyectable).
- Fallback determinista garantiza que el sistema no rompe si LLM falla.
- Shadow mode como primitiva: predice sin ejecutar; registro de `PrediccionAgente` para eval continua.
- Eval suite de 50 casos dorados con target de precisión >= 80% (actual: 92% fallback).
- Multi-proveedor: cambiar de Claude a GPT requiere un cambio en la clase del agente, no en la infraestructura.

**Negativas:**
- Sin utilidades de orquestación listas: cadenas de agentes, memoria a largo plazo, herramientas estándar se escriben a mano.
- Requiere más código propio que LangChain.

**Neutrales:**
- La complejidad de agentes multi-step se maneja en Fase 2 cuando haya casos reales que lo justifiquen.

## Cómo revisitar esta decisión

Si en Fase 1 se necesitan agentes con más de 5 herramientas encadenadas o memoria persistente entre conversaciones, re-evaluar LangGraph (solo el grafo, no el ecosistema completo).
