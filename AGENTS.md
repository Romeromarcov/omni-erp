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
- **PRs** en draft; el agente nunca marca "ready". Code review humano obligatorio.

El objetivo del gate: **cada avance queda 100 % sólido y no hay que retroceder**.
