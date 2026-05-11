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

## Cómo se escriben

Ver plantilla en el plan operativo del proyecto, Apéndice B.2.

## Cómo se revisitan

Los ADRs se revisan en cada checkpoint trimestral. Si una decisión necesita cambiar, se crea un ADR nuevo que la reemplaza explícitamente; no se modifica el ADR original (es histórico).
