# Omni ERP — Instrucciones para agentes

Este archivo lo lee **todo agente** (Claude Code, Cursor, Codex…) y todo colaborador al
entrar al repo. Léelo completo antes de tocar código.

## Antes de empezar

1. **Fuente de verdad:** [`docs/PLAN_MAESTRO_UNICO.md`](docs/PLAN_MAESTRO_UNICO.md) es el
   único documento de planificación. Lee al menos su **§2 — Reglas inviolables**
   (R-CODE / R-PROC / R-PROD) antes de escribir nada.
2. **Reglas que no se violan:** multi-tenant siempre (R-CODE-1), PostgreSQL nunca SQLite
   (R-CODE-2), Decimal para dinero (R-CODE-4), sin secretos en código/logs (R-CODE-8),
   PRs pequeños y focales (R-PROC-2), code review humano obligatorio (R-PROC-3).
3. **Skills del proyecto:** revisa `docs/skills/` (módulos Django, aislamiento multi-tenant,
   dinero Decimal, fiscal Venezuela, disciplina de PR).

## ⛔ Gate de cierre obligatorio (Definition of Done)

**Ningún cambio se considera terminado hasta pasar el gate completo.** El objetivo es que
**cada avance quede 100 % sólido y no haya que retroceder** — sin acumular deuda técnica.

Antes de declarar "listo", "terminado" o de abrir/actualizar un PR, corre **en orden**:

1. **Build verde** — `cd backend && python manage.py check && python manage.py makemigrations --check --dry-run`; `cd frontend && npx tsc -b && npm run lint`
2. **Tests verdes** — `python -m pytest tests_api/` (backend) + `npm test -- --run` (frontend); `tests_eval/` si tocas agentes
3. **Revisión de seguridad** — `/security-review` (secretos, multi-tenant, authz, `str(e)`, inyección)
4. **Revisión de bugs / correctness** — `/code-review` (casos borde, Decimal, atomicidad, N+1)
5. **Revisión de gaps** — ¿qué quedó a medias? Flujos abiertos, tests faltantes, `TODO` sin dueño
6. **Cero deuda nueva** — o un Compromiso Técnico Fechado en `docs/ctf/` con `vence_en` y dueño
7. **Auto-checklist R-CODE/R-PROC** con honestidad (skill `omni-pr-discipline`)

Si un paso falla, **se arregla antes de continuar** — nunca "para el próximo PR".

👉 El detalle completo, con todos los comandos y checklists, está en
**[`docs/DEFINITION_OF_DONE.md`](docs/DEFINITION_OF_DONE.md)**. Es de lectura obligatoria.

## Convenciones rápidas

- **Commits:** español, imperativo, descriptivos (`agrega…`, `corrige…`, `refactoriza…`).
- **PRs:** se abren en **draft**; el agente **nunca** marca "ready" (lo hace el revisor humano).
- **Plantilla de PR y auto-checklist:** [`docs/skills/omni-pr-discipline/SKILL.md`](docs/skills/omni-pr-discipline/SKILL.md).
- **Auditorías:** planificación y logs en [`docs/auditorias/`](docs/auditorias/); finalizadas en `docs/auditorias/archivo/`.
