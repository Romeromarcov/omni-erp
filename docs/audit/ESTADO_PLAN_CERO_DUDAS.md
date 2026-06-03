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

### Avance sesión 2026-06-03 (rama `fix/audit-2026-06-01`)
- **Bug real corregido:** BUG-1 (`UnboundLocalError` de Decimal en pago en divisa, `ventas/views.py`).
- **Tests nuevos verificados:** TEST-1 (aislamiento auto-descubierto, ~99 ViewSets), TEST-3
  (property-based IVA/IGTF), TEST-4 (race de reserva de stock).
- **Gates endurecidos (CI verde):** ruff bugs reales (E9/F63/F7/F82/F823) bloqueante, 4 reglas
  semgrep propias bloqueantes (`.semgrep.yml`), diff-cover ≥90% bloqueante en PR.
- **Cobertura:** ratchet 65→67 (medido 68.06%, 1084 tests verdes).
- **Hallazgos documentados:** BUG-DUP-1 (clases/ViewSet duplicados en finanzas, sin corregir —
  requiere PR con tests de API). SEC-1 verificado (sub-fetch acotado, requiere decisión).
- **3 "bugs críticos" del assessment refutados** con evidencia (atomicidad factura, scope `*` MCP,
  soft-delete).

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
- **TEST-1 — Aislamiento multi-tenant auto-descubierto (máximo ROI). ✅ HECHO.**
  `tests_api/test_aislamiento_cobertura.py` introspecta el URLconf y verifica que los ~99
  ViewSets sobre modelos con FK a `Empresa` sobreescriben `get_queryset`; **falla solo si se
  añade un ViewSet sin aislamiento**. Blinda R-CODE-1 para siempre. Verificado local (99
  passed, 1 skip por allowlist). *Pendiente complementario:* variante de comportamiento
  (cross-tenant 404/403) cuando se construya la estructura `tests/` (TEST-2).
- **A1-3 — Tercera matriz** `MAPA_MCP_CELERY_COMMANDS.md` + columnas faltantes en las dos
  existentes (`test_authz`, `en_openapi`, `unique_together`, `test_aislamiento`). Regenerada en CI.
- **A4-1 — `docs/tech-debt/INVENTORY.md`. ✅ HECHO.** Inventario con 3 TODO de frontend
  (verificados), deuda arquitectónica (§4.3), deuda de tooling y enlaces a auditorías.
- **A5-1 — Corregir §4.2 del Plan Maestro. ✅ HECHO.** Eliminadas apps fantasma
  (`logistica_transporte`, `flota`, `control_calidad`), añadidas `gestion_aprobaciones`/
  `localizacion`, corregido `vzla_localizacion`→`localizacion_ve` (líneas 293, 359, 369).
- **A2-1 — Consolidar** `AUDITORIA_2026-06-02.md` → `docs/audit/SECURITY_REVIEW_2026-06-02.md`
  con formato DoD A2 (severidad + CWE + archivo:línea + estado).

### Seguridad residual (verificar y, si procede, fijar)
- **SEC-1 — `user.empresa` singular en el asistente IA. ⚠️ VERIFICADO (acotado).** Los únicos
  usos reales están en `apps/agentes/api/chat.py:69,81,105` (herramientas read-only del chat:
  aging, buscar_cliente, saldo_cliente). **No es fuga cross-tenant** (filtra *a* una empresa,
  no expone otras); es un **sub-fetch**: para un usuario multi-empresa el asistente sólo ve
  `empresas.first()`. `cxc/cobranza` ya usa `get_empresas_visible` (comentario explícito en
  `cobranza.py:24`). **Requiere decisión de diseño**, no parche: ¿el asistente opera sobre una
  empresa explícita del contexto de conversación (validada contra `get_empresas_visible`), o
  agrega? No se toca a ciegas.
- **SEC-2 — COOP/CORP headers** en ambos nginx (`Cross-Origin-Opener-Policy`/`-Resource-Policy`).
- **SEC-3 — CSP**: endurecer `script-src 'unsafe-inline'` (Report-Only + nonces).

### Tooling / gates (días)
- **A0-1 — `.semgrep.yml` versionado. ✅ HECHO (parcial).** 4 reglas propias bloqueantes
  (`raw/extra SQL`, `verify=False`, `eval/exec`, `subprocess shell=True`), verificadas
  limpias (0 findings/616 archivos) y cableadas en el job semgrep de CI. *Pendiente:*
  `mypy.ini`/`pyproject.toml` con config estricta en módulos de dinero.
- **A0-2** — `pytest -n auto` (xdist ya instalado) para acortar la suite.
- **GATE-1 — escalar gates a bloqueante. 🟡 EN CURSO.** ✅ `ruff` bugs reales (E9/F63/F7/F82/
  **F823**) ahora bloqueante; ✅ reglas semgrep propias bloqueantes. *Pendiente:* `mypy`
  (módulos críticos), `diff-cover` (PR), `pip-audit`/`npm audit`/`trivy` (High/Critical),
  `ruff` F401/F811 (tras limpiar — bloquea BUG-DUP-1).
- **A0-3** — instalar y cablear `drf-spectacular`/`drf-yasg` (OpenAPI), `schemathesis` (job
  `contract`), `mutmut` (workflow `nightly`), `safety`, `eslint-plugin-security`.

### Cimientos de test (semanas)
- **TEST-2** — estructura `backend/tests/{factories,unit,integration,tenant,api,e2e}` + migración.
- **TEST-3 — property-based con `hypothesis`. ✅ HECHO (inicial).** `test_property_fiscal.py`:
  invariantes de IVA/IGTF (sumas exactas, no-negatividad, redondeo 2 decimales, aplicabilidad
  IGTF) sobre ~1300 casos generados. *Ampliar:* aging, scoring, stock, pagos mixtos.
- **TEST-4 — race tests (`select_for_update`). 🟡 EN CURSO.** ✅ `test_inventario_concurrencia.py`
  (reserva de stock: no overselling, verificado) + el existente `test_fiscal_concurrencia.py`
  (correlativos). *Pendiente:* saldos CxC/CxP.
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
