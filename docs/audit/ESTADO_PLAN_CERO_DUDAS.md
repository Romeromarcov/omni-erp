# Estado de ejecución — Plan "Cero Dudas" (auditoría + testing)

> Seguimiento de [`docs/PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md`](../PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md).
> Cada ítem se cierra con **CI verde** y bajo el [gate de cierre](../DEFINITION_OF_DONE.md).
>
> **Última evaluación:** 2026-06-02 (10 subagentes read-only + verificación adversarial manual).
> **Rama de trabajo:** `fix/audit-2026-06-01`.

## Veredicto honesto

El plan está **parcialmente implementado**: la **Fase 0 (tooling + mapa)** y buena parte de la
**Fase 1 (seguridad)** están hechas y sólidas (PR #6/#7). El criterio de "cero dudas" (cobertura
90/80, mutation ≥80%, contract fuzzing, E2E, gates bloqueantes) **todavía NO se cumple** — es el
grueso de las Fases 2–5, estimado en semanas. **No se debe afirmar "100% / cero dudas" aún.**

### ⚠️ Falsos positivos del assessment automático (verificados a mano)

La evaluación por agentes sobredimensionó tres hallazgos. Verificación línea por línea:

| Hallazgo del agente | Veredicto real | Evidencia |
|---|---|---|
| R-CODE-11: `emitir_factura_fiscal()` no atómico | **FALSO** — sí lo es | `apps/ventas/services.py:378` tiene `@transaction.atomic` sobre factura + asiento |
| SEC-NEW-4: scope `*` de MCP no bloqueado | **YA RESUELTO** | `apps/core/mcp_server.py:115-121` filtra `*` salvo `comodin_autorizado` |
| R-CODE-6: 27 apps "no filtran soft-delete" | **SOBREDIMENSIONADO** | Mostrar inactivos en la API de gestión es intencional; R-CODE-6 prohíbe *hard delete*, no obliga a ocultar `activo=False`. Revisar caso por caso, no en bloque |

**Lección (consistente con el gate):** todo hallazgo se verifica adversarialmente antes de actuar.

---

## Estado por fase

| Fase | DoD | Estado | Nota |
|---|---|---|---|
| **0 · Tooling + mapa** | herramientas en CI, matrices A1, diff-cover | 🟡 ~80% | tooling instalado pero varios `continue-on-error`; falta 3ª matriz |
| **1 · Seguridad** | reporte sin High/Critical abiertos, CTFs | 🟡 sustancial | auditoría en `AUDITORIA_2026-06-02.md`; faltan 2 residuales reales (ver SEC-*) |
| **2 · Cimientos de test** | aislamiento parametrizado, contract-drift | 🔴 falta | aislamiento es manual, no auto-descubierto; sin contract |
| **3 · Backfill** | cobertura 90% + mutation ≥80% | 🔴 falta | cobertura backend 65%, frontend ~55%; sin mutation |
| **4 · E2E + frontend** | flujos E2E verdes | 🔴 falta | sin Playwright; FE en ~55% |
| **5 · Endurecer gates** | jobs bloqueantes + branch protection | 🔴 falta | varios gates en `continue-on-error` |

Leyenda: 🟢 hecho · 🟡 parcial · 🔴 pendiente.

---

## Backlog priorizado (por ROI, cada uno = 1 PR con gate)

### Quick wins verificables (horas–días)
- **TEST-1 — Aislamiento multi-tenant parametrizado (máximo ROI).** Un único
  `tests/tenant/test_aislamiento.py` que introspecta el router DRF y prueba cross-tenant
  TODOS los ViewSets tenant; **falla solo si se añade un ViewSet sin aislamiento**. Blinda
  R-CODE-1 para siempre. *(Requiere correr la suite con Postgres para validar.)*
- **A1-3 — Tercera matriz** `MAPA_MCP_CELERY_COMMANDS.md` + columnas faltantes en las dos
  existentes (`test_authz`, `en_openapi`, `unique_together`, `test_aislamiento`). Regenerada en CI.
- **A4-1 — `docs/tech-debt/INVENTORY.md`** (hoy vacío): inventariar 3 TODO de frontend + ítems
  BAJA/MEDIA históricos; enlazar desde `docs/ctf/`.
- **A5-1 — Corregir §4.2 del Plan Maestro**: quitar apps fantasma (`logistica_transporte`,
  `flota`, `control_calidad`), añadir `gestion_aprobaciones`/`localizacion`, corregir
  `vzla_localizacion`→`localizacion_ve`.
- **A2-1 — Consolidar** `AUDITORIA_2026-06-02.md` → `docs/audit/SECURITY_REVIEW_2026-06-02.md`
  con formato DoD A2 (severidad + CWE + archivo:línea + estado).

### Seguridad residual (verificar y, si procede, fijar)
- **SEC-1 — `request.user.empresa` singular** en `cxc/cobranza/cartera/agente/fraccionamiento`:
  confirmar si rompe multi-empresa y migrar a `get_empresas_visible()`. *(Verificar primero.)*
- **SEC-2 — COOP/CORP headers** en ambos nginx (`Cross-Origin-Opener-Policy`/`-Resource-Policy`).
- **SEC-3 — CSP**: endurecer `script-src 'unsafe-inline'` (Report-Only + nonces).

### Tooling / gates (días)
- **A0-1** — `.semgrep.yml` versionado; `mypy.ini`/`pyproject.toml` con config estricta en
  módulos de dinero (`contabilidad`, `finanzas`, `nomina`).
- **A0-2** — `pytest -n auto` (xdist ya instalado) para acortar la suite.
- **GATE-1** — escalar a bloqueante (quitar `continue-on-error`) **uno por uno y solo cuando
  el check pase limpio**: `ruff`, `mypy` (módulos críticos), `diff-cover` (PR), `pip-audit`/
  `npm audit`/`trivy` (High/Critical).
- **A0-3** — instalar y cablear `drf-spectacular` (OpenAPI), `schemathesis` (job `contract`),
  `mutmut` (workflow `nightly`), `safety`, `eslint-plugin-security`.

### Cimientos de test (semanas)
- **TEST-2** — estructura `backend/tests/{factories,unit,integration,tenant,api,e2e}` + migración.
- **TEST-3** — property-based con `hypothesis` (instalado, sin usar) para invariantes de dinero.
- **TEST-4** — race tests (`select_for_update`) para stock, saldos CxC/CxP, correlativos.
- **TEST-5** — integración de flujos críticos faltantes: compra, cobranza, manufactura.
- **TEST-6** — frontend: MSW (instalado, sin usar), `openapi-typescript` + drift, Playwright E2E,
  pisos de cobertura por carpeta.

### Backfill de cobertura (semanas, por ratchet)
- **COV-1** — subir `--cov-fail-under` por escalones 65→75→85→90 (backend) conforme entra backfill.
- **COV-2** — subir thresholds vitest 55→65→75→80 (frontend).
- **COV-3** — `diff-cover --fail-under=95` bloqueante en PR.
- **MUT-1** — `mutmut` score ≥80% en módulos críticos (job nightly).

---

## Camino crítico recomendado

1. **TEST-1** (aislamiento parametrizado) + **GATE-1 parcial** (`diff-cover` bloqueante en PR)
   → blinda el futuro: nada nuevo entra sin test ni sin aislamiento.
2. Quick wins de documentación (A1-3, A4-1, A5-1, A2-1) → cierran DoDs de bajo riesgo.
3. Verificar y fijar SEC-1..3.
4. Backfill incremental de cobertura por app priorizada (dinero/contable primero).
5. Endurecer gates restantes y branch protection al final.

> **Importante:** cada ítem entra como PR propio, pequeño y focal (R-PROC-2), con el
> [gate de cierre](../DEFINITION_OF_DONE.md) completo. "Cero dudas" se alcanza cuando todos
> los ítems están 🟢 y los gates de CI son bloqueantes — no antes.
