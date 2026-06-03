# Definition of Done — Gate de cierre obligatorio

> **Regla de oro:** ningún feature, fix o cambio se considera **terminado** hasta pasar
> este gate completo. El objetivo es que **cada avance quede 100 % sólido y no haya que
> retroceder**: nada de acumular deuda técnica, bugs silenciosos, ni huecos de seguridad
> que aparezcan después.
>
> Este documento es la **fuente única** del gate (R-PROC-1). Las reglas que valida
> (R-CODE-*, R-PROC-*) viven en [`docs/PLAN_MAESTRO_UNICO.md` §2](PLAN_MAESTRO_UNICO.md#2--reglas-inviolables-del-proyecto).

## Quién debe cumplirlo

**Todo** el que toque el repo: el founder, cualquier agente de IA (Claude, Cursor, Codex…)
y cualquier colaborador humano. Si estás por declarar "listo", "terminado", "ready" o por
abrir/actualizar un PR, **primero corres este gate**.

---

## El gate (7 pasos, en orden)

Ninguno es opcional. Si un paso falla, **se arregla antes de continuar** — no se difiere
"para el próximo PR" (R-PROC-7: la deuda no se pospone).

### 1. Compilación / build verde

Mismo comando que valida CI (`.github/workflows/ci.yml`), para no descubrir en CI lo que
se pudo ver local.

```bash
# Backend
cd backend
python manage.py check                          # Django system check
python manage.py makemigrations --check --dry-run   # sin drift de migraciones (NEW-MIG-1)

# Frontend
cd ../frontend
npx tsc -b        # type-check en modo build (idéntico a `npm run build`)
npm run lint      # ESLint
```

### 2. Tests verdes

```bash
# Backend
cd backend
python -m pytest tests_api/ -v --tb=short --no-header
# Si tocaste agentes / lógica de reorden o cobranza:
python -m pytest tests_eval/ -v --tb=short --no-header --no-cov   # umbral precision@1 ≥ 80% (CTF-003)

# Frontend
cd ../frontend
npm test -- --run
```

- **Flaky = bug** (R-PROC-4). Se arregla, no se reintenta hasta que pase por suerte.
- **Tests en el mismo cambio**, no "después" (R-CODE-9). Flujo crítico
  (venta → factura → stock → asiento → CxC) debe seguir verde.
- Todo feature nuevo trae sus tests; multi-tenant trae **test de aislamiento** (R-CODE-1).

### 3. Revisión de seguridad

Corre `/security-review` sobre el diff, **o** verifica manualmente:

- [ ] **Sin secretos** en código ni logs (R-CODE-8). Nada de API keys, passwords, tokens.
- [ ] **Aislamiento multi-tenant** (R-CODE-1): todo `get_queryset()` filtra por la empresa
      del usuario. Sin fugas entre tenants.
- [ ] **AuthZ**: cada endpoint nuevo valida permisos; nada queda abierto por defecto.
- [ ] **Sin `str(e)` al cliente** en errores 500 (R-CODE-8); se loguea con `logger.exception`.
- [ ] **Inputs validados**: sin inyección (SQL/ORM raw, shell, template), sin XSS en frontend.
- [ ] **Dependencias** nuevas: justificadas, sin vulnerabilidades conocidas conocidas.

### 4. Revisión de bugs / correctness

Corre `/code-review` sobre el diff, **o** verifica manualmente:

- [ ] Casos borde cubiertos (vacíos, nulos, cero, negativos, concurrencia).
- [ ] **Decimal para dinero**, nunca `float` (R-CODE-4); redondeo correcto.
- [ ] Transacciones atómicas donde haya múltiples escrituras; asiento contable en la
      misma `@transaction.atomic` (R-CODE-11).
- [ ] Sin condiciones de carrera, sin N+1 en rutas calientes.
- [ ] Manejo de errores explícito; nada de `except: pass` silencioso.

### 5. Revisión de gaps (¿qué falta?)

La pregunta honesta: **"¿qué dejé a medias?"**

- [ ] ¿Hay un flujo abierto a medias? → Cerrar el flujo primero (§2.4 del Plan Maestro).
- [ ] ¿Falta UI, API o capacidad MCP del feature? (API-first, R-CODE-7).
- [ ] ¿Faltan migraciones reversibles? (R-PROC-5).
- [ ] ¿Quedaron `TODO` / `FIXME` sin dueño? → Conviértelos en CTF o resuélvelos.
- [ ] ¿Documentación / `PROJECT_LOG.md` desactualizados por este cambio?

### 6. Deuda técnica: cero nueva sin compromiso fechado

- [ ] No se introduce deuda nueva. Si es **inevitable**, se registra como
      **Compromiso Técnico Fechado** en `docs/ctf/` con `vence_en` y `dueño` (R-PROC-6).
- [ ] Sin código de debug (`print`, `console.log`, `debugger`, `pdb`) — R-CODE-3.

### 7. Reglas R-CODE / R-PROC verificadas con honestidad

Marca el auto-checklist de [`omni-pr-discipline`](skills/omni-pr-discipline/SKILL.md) sin
mentir. Un check marcado sin verificar rompe la confianza del revisor (anti-patrón 5 del skill).

---

## Después del gate

- **PR en draft.** El agente **nunca** marca "ready"; lo hace el revisor humano (R-PROC-3).
- **Code review humano obligatorio**, aunque el código lo escriba un agente. Auto-merge de
  PR de agente está prohibido.
- CI verde es no-negociable (R-PROC-4); el gate local existe para que CI **nunca** sea la
  primera vez que se ve un fallo.

## Por qué este gate existe

Sin él, cada feature deja un pequeño residuo (un test que falta, un caso borde, un hueco de
authz). Esos residuos se acumulan como deuda técnica y, tarde o temprano, obligan a
**retroceder** sobre trabajo que se creía terminado. El gate convierte "terminado" en una
afirmación verificable: cada avance es un punto al que **no hay que volver**.

## Referencias

- Reglas inviolables: [`PLAN_MAESTRO_UNICO.md` §2](PLAN_MAESTRO_UNICO.md#2--reglas-inviolables-del-proyecto)
- Disciplina de PR + plantilla: [`skills/omni-pr-discipline/SKILL.md`](skills/omni-pr-discipline/SKILL.md)
- Compromisos Técnicos Fechados: [`docs/ctf/`](ctf/)
- CI: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)
