# ADR-005: DSL de Personalización Declarativo — 6 Primitivas YAML/JSON

**Estado:** Aceptado
**Fecha:** 2026-05-16
**Autor(es):** Marco Romero, Claude Sonnet 4.6

## Contexto

WS-5 de Fase 0 requiere diseñar e implementar el DSL de personalización (R-PROD-2, A-014). El sistema debe permitir que un usuario no técnico adapte su instancia del ERP sin tocar código.

Los criterios irrenunciables (de la PARTE I del plan):
- Declarativo: el usuario habla, el agente (en Fase 1) traduce a DSL.
- Versionable: cada config tiene versión, se puede hacer rollback.
- Reversible: aplicar una personalización no es destructivo.
- Validable: antes de aplicar se detectan errores.
- Sin código generado: las reglas son datos, no Python.

## Decisión

**DSL con 6 primitivas jerárquicas, expresadas como dict Python (serializable a YAML o JSON).**

Las 6 primitivas:

| Primitiva   | Propósito                                         | Estado Fase 0 |
|-------------|---------------------------------------------------|---------------|
| `campos`    | Renombrar, ocultar, requerir, agregar campos      | PoC funcional |
| `entidades` | Definir nuevos tipos de entidad custom            | Spec + validator |
| `estados`   | Agregar estados a workflows existentes            | Spec + validator |
| `reglas`    | Validaciones declarativas antes de guardar        | Spec + validator |
| `vistas`    | Personalizar columnas y filtros de listas         | Spec + validator |
| `conectores`| Webhooks hacia sistemas externos                  | Spec + validator |

El validador está implementado y cubre errores de tipo, entidades inválidas, operadores inválidos y estructuras incompletas. El aplicador (PoC) procesa la primitiva `campos` completamente; las demás quedan como "registradas" hasta Fase 1.

`PersonalizacionConfig` persiste cada versión en BD (historial para rollback).

## Alternativas consideradas

1. **JSON Schema puro** — descartada porque: el ecosistema de validación en Python requiere `jsonschema` (dependencia extra); el mensaje de error es críptico para usuarios no técnicos; difícil de extender con validaciones cruzadas.
2. **Pydantic models** — descartada porque: acoplamiento fuerte al modelo Python; las personalizaciones del usuario deben viajar como datos (YAML/JSON), no como código.
3. **DSL con sintaxis propia (parser)** — descartada porque: costo de mantenimiento del parser; los LLMs no pueden generar YAML correcto más fácilmente que Python/JSON.

## Consecuencias

**Positivas:**
- Config expresable como YAML humano-legible, JSON para API, dict Python para tests.
- Validador 100% testeable sin DB (pure Python).
- Extensible: agregar primitiva = agregar función `_validar_nueva()` y case en `validar_config()`.
- Versionado natural: `PersonalizacionConfig.version` permite historial y rollback.

**Negativas:**
- Primitiva `entidades` requiere modelo EAV en BD para Fase 1 (no hay migración de datos hoy).
- Primitivas `reglas` y `conectores` no se ejecutan en Fase 0 (solo se validan y registran).

**Neutrales:**
- El agente de personalización conversacional (Fase 1) solo necesita llamar `validar_config()` antes de guardar — la interfaz ya está estabilizada.

## Cómo revisitar esta decisión

Si en Fase 1 el agente de personalización genera configs que el validador rechaza con frecuencia por limitaciones del DSL, se extiende el conjunto de primitivas/operadores, no se cambia el mecanismo.
