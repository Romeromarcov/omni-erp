---
name: omni-definition-of-done
description: Use this skill whenever you are about to declare a change "done", "ready", or "finished", or before opening/updating a PR in the Omni project. Triggers include reaching the end of an implementation, preparing to hand off work, the user saying "listo"/"terminado"/"ya quedó", or any moment you would otherwise stop after writing code. Apply it to run the mandatory closing gate (build, tests, security, correctness, gaps, zero new debt, rule self-checklist) IN ORDER before considering anything complete. Do NOT use during early design/exploration, or for pure documentation that does not go through PR review.
---

# Skill: Gate de Cierre (Definition of Done)

## Cuándo usar esta skill

Cargá esta skill **antes de declarar cualquier cambio "terminado"** o de abrir/actualizar un PR. Es el último paso de toda tarea de implementación.

No la cargués en fase de diseño/exploración temprana, ni para documentación que no pasa por PR.

## La regla de oro

> **Ningún feature, fix o cambio está terminado hasta pasar el gate completo.** El objetivo es que **cada avance quede 100% sólido y no haya que retroceder** — sin acumular deuda técnica, bugs silenciosos ni huecos de seguridad.

Si un paso falla, **se arregla antes de continuar** — nunca "para el próximo PR" (R-PROC-7).

## El gate: 7 pasos en orden

### 1. Build verde

```bash
# Backend
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run    # sin drift de migraciones

# Frontend (si lo tocaste)
cd ../frontend
npx tsc -b
npm run lint
```

### 2. Tests verdes

```bash
cd backend
python -m pytest tests/ -v --tb=short --no-header
# Si tocaste agentes / reorden / cobranza:
python -m pytest tests_eval/ -v --tb=short --no-header --no-cov   # precision@1 ≥ 80%

cd ../frontend
npm test -- --run
```

- Flaky = bug (R-PROC-4): se arregla, no se reintenta.
- Tests en el mismo cambio (R-CODE-9); flujo crítico (venta→factura→stock→asiento→CxC) sigue verde.
- Multi-tenant trae test de aislamiento (R-CODE-1).
- Ver `omni-testing-pytest`.

### 3. Revisión de seguridad

Corré `/security-review` sobre el diff, **o** verificá manualmente:
- [ ] Sin secretos en código ni logs (R-CODE-8).
- [ ] Aislamiento multi-tenant: todo `get_queryset()` filtra por la empresa del usuario (R-CODE-1).
- [ ] AuthZ: cada endpoint nuevo valida permisos; nada abierto por defecto.
- [ ] Sin `str(e)` al cliente en errores 500; se loguea con `logger.exception` (R-CODE-8).
- [ ] Inputs validados: sin inyección (SQL/ORM raw, shell, template), sin XSS.
- [ ] Dependencias nuevas justificadas, sin CVEs conocidos.

Ver `omni-multi-tenant-isolation`.

### 4. Revisión de bugs / correctness

Corré `/code-review` sobre el diff, **o** verificá manualmente:
- [ ] Casos borde: vacíos, nulos, cero, negativos, concurrencia.
- [ ] Decimal para dinero, nunca float; redondeo correcto (R-CODE-4, ver `omni-decimal-money`).
- [ ] Transacciones atómicas donde hay múltiples escrituras; asiento contable en la misma `@transaction.atomic` (R-CODE-11, ver `omni-asientos-contables`).
- [ ] Sin races, sin N+1 en rutas calientes.
- [ ] Manejo de errores explícito; nada de `except: pass` silencioso.

### 5. Revisión de gaps (¿qué quedó a medias?)

La pregunta honesta: **"¿qué dejé incompleto?"**
- [ ] ¿Hay un flujo abierto a medias? → Cerralo primero.
- [ ] ¿Falta UI, API o capacidad MCP del feature? (API-first, R-CODE-7 = REST + MCP, ver `omni-mcp-capacidades`).
- [ ] ¿Faltan migraciones reversibles? (R-PROC-5).
- [ ] ¿Quedaron `TODO`/`FIXME` sin dueño? → Convertilos en CTF o resolvelos.
- [ ] ¿Documentación / `PROJECT_LOG.md` desactualizados por este cambio?

### 6. Cero deuda nueva sin compromiso fechado

- [ ] No se introduce deuda nueva. Si es **inevitable**, se registra como Compromiso Técnico Fechado en `docs/ctf/` con `vence_en` y `dueño` (R-PROC-6, ver `omni-ctf-deuda`).
- [ ] Sin código de debug: `print`, `console.log`, `debugger`, `pdb` (R-CODE-3).

### 7. Reglas R-CODE / R-PROC verificadas con honestidad

Marcá el auto-checklist de `omni-pr-discipline` sin mentir. Un check marcado sin verificar rompe la confianza del revisor.

## Después del gate

- **PR en draft.** El agente **nunca** marca "ready"; lo hace el revisor humano (R-PROC-3).
- **Code review humano obligatorio**, aunque el código lo escriba un agente. Auto-merge de PR de agente está prohibido.
- CI verde es no-negociable (R-PROC-4); el gate local existe para que CI **nunca** sea la primera vez que se ve un fallo.

## Cómo aplicarla en la práctica

1. Cuando creas que terminaste, **no lo declares todavía**. Abrí esta skill.
2. Corré los pasos 1→7 **en orden**. No saltes al PR si el paso 2 falla.
3. Si un paso revela trabajo, hacelo ahora (no lo difieras).
4. Solo cuando los 7 pasan, preparás el PR con `omni-pr-discipline`.

> Decir "listo" sin haber corrido el gate es el error que esta skill existe para prevenir. "Terminado" es una afirmación **verificable**, no una sensación.

## Anti-patrones

### Anti-patrón 1: declarar "listo" sin correr el gate
**Antídoto:** el gate es la definición de "listo". Sin él, no está listo.

### Anti-patrón 2: saltar pasos porque "este cambio es chico"
**Antídoto:** los cambios chicos también filtran secretos y rompen aislamiento. El gate aplica a todo.

### Anti-patrón 3: diferir un fallo "para el próximo PR"
**Antídoto:** R-PROC-7. Se arregla ahora o se registra como CTF fechado; no se pospone informalmente.

### Anti-patrón 4: marcar el PR como ready
**Antídoto:** el agente abre en draft; el humano decide ready (R-PROC-3, ver `omni-pr-discipline`).

## Checklist final (resumen del gate)

- [ ] 1. Build verde (backend `check` + `makemigrations --check`; frontend `tsc -b` + `lint`).
- [ ] 2. Tests verdes (pytest + eval si aplica + frontend).
- [ ] 3. Seguridad revisada (`/security-review` o manual).
- [ ] 4. Correctness revisada (`/code-review` o manual).
- [ ] 5. Gaps cerrados (flujos, API/MCP, migraciones, TODOs, docs).
- [ ] 6. Cero deuda nueva (o CTF fechado); sin código de debug.
- [ ] 7. Auto-checklist R-CODE/R-PROC marcado con honestidad.
- [ ] PR en draft; nunca ready.

## Referencias

- Fuente: `docs/DEFINITION_OF_DONE.md` (gate completo), `CLAUDE.md` (puerta de entrada).
- Skill: `omni-pr-discipline`, `omni-testing-pytest`, `omni-multi-tenant-isolation`, `omni-ctf-deuda`, `omni-asientos-contables`, `omni-mcp-capacidades`.
- Reglas R-CODE-* y R-PROC-* del Plan Maestro §2.

## Changelog

### v1.0
- Versión inicial, basada en `docs/DEFINITION_OF_DONE.md`.
