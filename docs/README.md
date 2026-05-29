# Documentación — Omni ERP

Índice de toda la documentación del repositorio. Empieza por el plan maestro si te incorporas al proyecto.

## Punto de partida

- **[`PLAN_MAESTRO_UNICO.md`](PLAN_MAESTRO_UNICO.md)** — Única fuente de verdad del producto: visión, reglas, arquitectura, estado real y roadmap. **Empieza aquí.**
- [`../README.md`](../README.md) — Cómo levantar y trabajar con el monorepo.

## Backend

- [`../backend/README.md`](../backend/README.md) — Setup, stack y comandos del backend.
- [`../backend/docs/ARQUITECTURA_BACKEND.md`](../backend/docs/ARQUITECTURA_BACKEND.md) — Mapa de las 36 apps, routing y convenciones.
- [`../backend/docs/CIRCULAR_IMPORTS_ANALYSIS.md`](../backend/docs/CIRCULAR_IMPORTS_ANALYSIS.md) — Capas de dependencia entre apps.
- **README por app:** cada `backend/apps/<nombre>/README.md` documenta sus modelos y endpoints.
- API en vivo (con `DEBUG`): Swagger `/api/docs/` · ReDoc `/api/redoc/`.

## Frontend

- [`../frontend/README.md`](../frontend/README.md) — Stack, estructura, routing por dominio, páginas, componentes, hooks, i18n, tests y CI. (Refactor en pausa; documentación al día con el árbol actual.)

## Decisiones de arquitectura (ADR)

[`decisions/`](decisions/) — registro de decisiones técnicas:

- [ADR-001](decisions/ADR-001-postgres-server-offline-clients.md) — PostgreSQL servidor + clientes offline.
- [ADR-002](decisions/ADR-002-arquitectura-modular-wedge.md) — Arquitectura modular (wedge).
- [ADR-003](decisions/ADR-003-integration-hub-mcp.md) — Integration Hub + MCP.
- [ADR-004](decisions/ADR-004-agent-stack-anthropic-sdk.md) — Stack de agentes (Anthropic SDK).
- [ADR-005](decisions/ADR-005-dsl-personalizacion-declarativo.md) — DSL de personalización declarativo.
- [ADR-006](decisions/ADR-006-asientos-contables-automaticos.md) — Asientos contables automáticos.

## Skills (guías de implementación reutilizables)

[`skills/`](skills/) — patrones que el equipo (humano + IA) debe seguir:

- `omni-decimal-money` — manejo de dinero con `Decimal`.
- `omni-django-module` — estructura estándar de una app Django.
- `omni-multi-tenant-isolation` — aislamiento multi-tenant.
- `omni-pr-discipline` — disciplina de PRs.
- `omni-venezuela-fiscal` — fiscalidad venezolana.

## Otros

- [`ctf/`](ctf/) — ejercicios/retos de seguridad (CTF) internos.
- [`tech-debt/`](tech-debt/) — registro de deuda técnica.
- [`_archive/`](_archive/) — **planes históricos archivados.** Material superado por el plan maestro; se conserva solo como referencia histórica, no refleja el estado actual.

## Registro de trabajo

- [`../backend/PROJECT_LOG.md`](../backend/PROJECT_LOG.md) — bitácora cronológica append-only de las sesiones de desarrollo.
