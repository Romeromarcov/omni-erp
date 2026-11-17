# Omni ERP — Instrucciones para agentes

Este archivo lo lee **todo agente** (Claude Code, Cursor, Codex…) y todo colaborador al
entrar al repo. Léelo completo antes de tocar código.

## Antes de empezar

1. **Fuente de verdad:** [`docs/PLAN_MAESTRO_UNICO.md`](docs/PLAN_MAESTRO_UNICO.md) es el
   único documento de planificación. Lee al menos su **§2 — Reglas inviolables**
   (R-CODE / R-PROC / R-PROD) antes de escribir nada.
2. **Reglas que no se violan:** multi-tenant siempre (R-CODE-1), PostgreSQL nunca SQLite
   (R-CODE-2), Decimal para dinero (R-CODE-4), sin secretos en código/logs (R-CODE-8),
   PRs pequeños y focales (R-PROC-2), revisión humana obligatoria en la puerta
   `develop`→`main` (R-PROC-3; los PRs a `develop` siguen el loop autónomo con Gate DoD +
   dictamen `APROBADO` de revisor independiente + CI 100 % verde).
3. **Skills del proyecto:** revisa `docs/skills/` (módulos Django, aislamiento multi-tenant,
   dinero Decimal, fiscal Venezuela, disciplina de PR).

## ⛔ Gate de cierre obligatorio (Definition of Done)

**Ningún cambio se considera terminado hasta pasar el gate completo.** El objetivo es que
**cada avance quede 100 % sólido y no haya que retroceder** — sin acumular deuda técnica.

Antes de declarar "listo", "terminado" o de abrir/actualizar un PR, corre **en orden**:

1. **Build verde** — `cd backend && python manage.py check && python manage.py makemigrations --check --dry-run`; `cd frontend && npx tsc -b && npm run lint`
2. **Tests verdes** — `python -m pytest tests/` (backend) + `npm test -- --run` (frontend); `tests_eval/` si tocas agentes
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
- **PRs a `develop` (loop autónomo autorizado por el owner, 2026-11-17):** se abren en `draft`. Tras pasar el **Gate DoD completo** y recibir dictamen **`APROBADO`** de un agente revisor **independiente y distinto del autor** (`QA + Seguridad`, evidenciado en comentario del PR), el agente/orquestador **marca el PR `ready`**, espera a que todos los checks de **CI estén 100 % verdes** y ejecuta el **merge a `develop`**.
- **PRs `develop`→`main` (puerta de producción):** siempre **revisión y aprobación humana obligatoria del owner (`R-PROC-3`)**. Ningún agente marca `ready` ni mergea a `main` sin aprobación humana.
- **Plantilla de PR y auto-checklist:** [`docs/skills/omni-pr-discipline/SKILL.md`](docs/skills/omni-pr-discipline/SKILL.md).
- **Auditorías:** planificación y logs en [`docs/auditorias/`](docs/auditorias/); finalizadas en `docs/auditorias/archivo/`.

## Grafo de conocimiento (Graphify)

Cuando exista `graphify-out/graph.json` (generado localmente e ignorado por Git junto a `.graphify*`), úsalo para reducir lectura innecesaria de archivos sin alterar ninguna regla `R-CODE-*`, `R-PROC-*` o `R-PROD-*`:

- **Antes de editar código:** consulta arquitectura, dependencias e impacto con:
  - `graphify query "<pregunta>"` — navegación BFS sobre entidades y relaciones relevantes.
  - `graphify explain "<concepto|módulo>"` — explicación de un nodo y sus conexiones.
  - `graphify affected "<archivo|símbolo>"` — trazado inverso de nodos impactados por un cambio.
- **Tras cada merge a `develop`:** ejecuta `graphify update .` (solo AST, sin costo LLM; los hooks locales instalados con `graphify hook install` también lo automatizan tras `commit`/`merge`/`checkout`).
- Las reglas y workflow para Antigravity viven en [`.agents/rules/graphify.md`](.agents/rules/graphify.md) y [`.agents/workflows/graphify.md`](.agents/workflows/graphify.md).

## 🌳 Flujo de trabajo y entornos (Git manda)

Detalle completo en **[`docs/FLUJO_DE_TRABAJO.md`](docs/FLUJO_DE_TRABAJO.md)**. Lo esencial:

- `main` = **producción** · `develop` = **staging** (ambos despliegan solos en Railway al merge).
- **Todo cambio (feature, fix, hotfix):** rama desde `develop` → PR `draft` a `develop` (Gate DoD + dictamen `APROBADO` de revisor independiente `QA + Seguridad` → `ready` → CI 100 % verde → merge a `develop`) → valida en staging → PR `develop`→`main` (**revisión y aprobación humana obligatoria del owner**) → prod. Nada salta directo a `main`.
- **Diagnóstico en staging/prod:** **solo lectura** (logs, datos) vía Railway CLI — skill [`docs/skills/diagnostico-railway/`](docs/skills/diagnostico-railway/SKILL.md). **Nunca** editar código ni datos en el contenedor (efímero); todo cambio vuelve por Git.
