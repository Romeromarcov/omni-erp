# Architectural Decision Records (ADRs)

Esta carpeta contiene las decisiones arquitectónicas mayores del proyecto Omni AI-Native, documentadas según el patrón ADR.

## Cuándo se crea un ADR

Se crea un ADR cuando se toma una decisión que:
- Afecta el comportamiento futuro del sistema en formas difíciles de revertir.
- Establece un patrón que se va a aplicar en muchos lugares.
- Resuelve una tensión o duda significativa que apareció en el proyecto.
- Es Nivel 3 del árbol de decisiones del plan operativo.

## Índice

| # | Título | Fecha | Estado |
|---|--------|-------|--------|
| 001 | PostgreSQL en Servidor + Offline-First en Clientes | 2026-05-10 | Aceptado |
| 002 | Arquitectura Modular y Estrategia Wedge | 2026-05-14 | Aceptado |
| 003 | Integration Hub Centralizado con MCP Bidireccional | 2026-05-14 | Aceptado |
| 004 | Stack Agéntico — Anthropic SDK + Orquestación Propia + Shadow Mode | 2026-05-16 | Aceptado |
| 005 | DSL de Personalización Declarativo — 6 Primitivas YAML/JSON | 2026-05-16 | Aceptado |
| 006 | Asientos Contables Automáticos Obligatorios (R-CODE-11) | 2026-05-16 | Aceptado |
| 007 | Arquitectura de Localización en Dos Capas | 2026-06-01 | Aceptado |
| 008 | Monorepo de Clientes + Shells Mobile y Desktop sobre la Capa 1 | 2026-06-01 | Aceptado |
| 009 | Separación entre cuentas_por_cobrar (ledger) y cxc (cobranza IA) | 2026-06-01 | Aceptado |
| 010 | Extensibilidad: escalera de customización L0–L4 y marketplace de plugins | 2026-06-12 | Aceptado |
| 011 | Servicios hermanos: fábrica de software y fábrica de marketing/contenido | 2026-06-12 | Aceptado |

## Cómo se escriben

Ver plantilla en el plan operativo del proyecto, Apéndice B.2.

## Cómo se revisitan

Los ADRs se revisan en cada checkpoint trimestral. Si una decisión necesita cambiar, se crea un ADR nuevo que la reemplaza explícitamente; no se modifica el ADR original (es histórico).
