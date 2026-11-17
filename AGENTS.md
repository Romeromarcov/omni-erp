# Omni ERP — Instrucciones para agentes

> Este proyecto usa **[`CLAUDE.md`](CLAUDE.md)** como archivo de instrucciones para agentes.
> Si tu herramienta (Cursor, Codex, etc.) lee `AGENTS.md` en vez de `CLAUDE.md`, **el
> contenido vigente está en [`CLAUDE.md`](CLAUDE.md)** — léelo completo.

## Lo esencial (resumen — el detalle está en `CLAUDE.md`)

- **Fuente de verdad de planificación:** [`docs/PLAN_MAESTRO_UNICO.md`](docs/PLAN_MAESTRO_UNICO.md), en especial **§2 Reglas inviolables**.
- **⛔ Gate de cierre obligatorio:** ningún cambio está "terminado" hasta pasar el
  **Definition of Done** — build verde, tests verdes, revisión de seguridad, de bugs, de
  gaps, cero deuda nueva. Detalle completo en
  **[`docs/DEFINITION_OF_DONE.md`](docs/DEFINITION_OF_DONE.md)**.
- **PRs hacia `develop`:** se abren en `draft`. Tras pasar el Gate DoD completo y recibir dictamen **`APROBADO`** de un agente revisor **independiente y distinto del autor** (`QA + Seguridad`, evidenciado en comentario del PR), el agente/orquestador **marca el PR `ready`**, espera a que todos los checks de **CI estén 100 % verdes** y ejecuta el **merge a `develop`** (autorizado por el owner, 2026-11-17).
- **PRs hacia `main` (`develop` → `main`):** puerta de producción con **revisión y aprobación humana obligatoria del owner (`R-PROC-3`)**. Ningún agente marca `ready` ni mergea a `main` sin aprobación humana.
- **Grafo de conocimiento (Graphify):** si `graphify-out/graph.json` existe, consulta dependencias y contexto con `graphify query`, `graphify explain` y `graphify affected` antes de editar código, y ejecuta `graphify update .` tras cada merge a `develop` (sin alterar las reglas `R-CODE-*`, `R-PROC-*` y `R-PROD-*`).

El objetivo del gate: **cada avance queda 100 % sólido y no hay que retroceder**.
