# Plan de Auditoría Exhaustiva + Arquitectura de Tests "Cero Dudas" — Omni ERP

**Objetivo:** llevar el proyecto a un estado donde se pueda afirmar, **con evidencia automatizada y reproducible**, que no quedan fallas de seguridad conocidas, bugs latentes en código crítico, ni deuda técnica sin rastrear — y que cada cambio futuro mantiene ese estándar.

**Por qué hace falta (límites del estado actual):**
- Las auditorías hechas hasta hoy son **búsqueda dirigida por patrones** (agentes que hacen grep/lectura de muestras), no verificación exhaustiva línea por línea.
- Cobertura de tests: **67% backend / 56% frontend** → ~1/3 del backend y ~44% del frontend **no se ejercitan**.
- El código nuevo de Ola 5 (nómina/manufactura) tiene testeado el **núcleo puro**, no las orquestaciones con BD.
- No hay análisis estático de seguridad (bandit/semgrep), de tipos (mypy), de CVEs de dependencias, ni mutation testing.

**Definición operativa de "cero dudas"** (criterio de cierre, todo en CI):
1. 0 hallazgos High/Critical sin resolver en `bandit`, `semgrep`, `pip-audit`, `npm audit`, `trivy`, `gitleaks`.
2. Cobertura backend ≥ **90%** y frontend ≥ **80%**, con **diff-coverage ≥ 95%** (todo código nuevo viene con test).
3. **Mutation score ≥ 80%** en módulos críticos (`contabilidad`, `fiscal`, `finanzas`, `ventas`, `compras`, `nomina`, `manufactura`, `cuentas_por_cobrar`, `cxc`).
4. **Todo modelo tenant-aware** tiene test de aislamiento cross-tenant (R-CODE-1) generado/parametrizado.
5. **Todo endpoint** tiene test de autorización + contrato (schema OpenAPI) verde; fuzzing de contrato (schemathesis) sin 500 inesperados.
6. **Flujos críticos E2E** verdes (web + API).
7. `mypy` sin errores en módulos de dinero/servicios; `tsc --strict` ya verde.
8. Firma de revisión de seguridad adversarial (no solo automatizada).

---

## PARTE A — Auditoría exhaustiva

### A0 · Tooling base (habilitar la evidencia) — *Fase 0*
Instalar y cablear en CI + pre-commit:

| Herramienta | Qué cubre | Dónde |
|---|---|---|
| `bandit` | seguridad estática Python (SQL, subprocess, crypto débil, asserts) | job CI + pre-commit |
| `semgrep` (rulesets `p/django`, `p/python`, `p/secrets`, `p/owasp-top-ten`) | patrones de vuln. y bugs | job CI |
| `ruff` | lint+formato rápido (reemplaza/aumenta flake8/black/isort) | pre-commit + CI |
| `mypy` (gradual, estricto en `services`/dinero) | tipos Python | job CI |
| `pip-audit` + `safety` | CVEs dependencias Python | job CI (ya parcial) |
| `npm audit` + `eslint-plugin-security` | CVEs + patrones JS | job CI (audit ya parcial) |
| `trivy` | CVEs de imágenes Docker + IaC + secretos | job CI sobre `backend/Dockerfile` y `frontend/Dockerfile.prod` |
| `gitleaks` | secretos en historial | ya en CI ✅ |
| `drf-spectacular` | esquema OpenAPI desde DRF | comando + drift-check |
| `schemathesis` | fuzzing del API contra el esquema | job CI |
| `mutmut` (o `cosmic-ray`) | mutation testing | job nightly |
| `diff-cover` | cobertura del diff del PR | job CI |
| `factory_boy` + `hypothesis` | fixtures + property-based | dependencia de test |
| `pytest-xdist` | paralelizar la suite (hoy ~6 min) | dev + CI |

**DoD A0:** todas instaladas, con configuración versionada (`pyproject.toml`/`setup.cfg`, `.semgrep.yml`, `mypy.ini`) y un job CI por herramienta (no-bloqueante al inicio, bloqueante al cerrar cada fase).

### A1 · Mapa de superficie (saber qué auditar) — *Fase 0*
Generar, con un management command de inventario, matrices versionadas:
- **Endpoints:** ruta → ViewSet/acción → permiso → ¿filtra tenant en `get_queryset`? → ¿tiene test de authz? → ¿en el esquema OpenAPI?
- **Modelos:** modelo → ¿tenant-aware (`id_empresa`)? → ¿`unique_together` correcto? → ¿UUIDv7? → ¿tiene test de aislamiento?
- **Tools MCP / Celery tasks / management commands / integraciones externas** → scope/tenant → test.

**DoD A1:** 3 matrices CSV/MD en `docs/audit/` que se regeneran en CI y sirven de checklist de cobertura de la auditoría (ninguna fila sin test marcado).

### A2 · Auditoría de seguridad adversarial (por dominio) — *Fase 1*
Revisión humana+IA guiada por la matriz A1, con checklist OWASP ASVS adaptado:

1. **AuthN** — ciclo JWT (access 15 min, refresh cookie httpOnly rotado + blacklist), rate-limit login/refresh, fuga en logs (R-CODE-8).
2. **AuthZ / multi-tenant (R-CODE-1)** — cada `get_queryset` y cada `@action`; IDOR por `pk`/`empresa_id` crudo; permisos a nivel de objeto; el patrón `get_empresas_visible` aplicado uniformemente.
3. **Inyección** — `.raw()`, `.extra()`, f-strings/format en queries, `RawSQL`; inyección en plantillas de cobranza; `subprocess`/`os.system` en commands.
4. **Secretos y config** — `settings_prod` fail-closed, sin defaults inseguros; cifrado en reposo (`EncryptedJSONField`/Fernet) y manejo de la clave; entropía de tokens.
5. **SSRF / externo** — Integration Hub (Odoo XML-RPC, BCV scrape, S3/MinIO, Binance) con verificación TLS y sin URLs controladas por el usuario sin validar; **toda salida HTTP por el Hub** (R).
6. **Carga de archivos** — whitelist + magic bytes + tamaño + path traversal + content-type forzado a `attachment`.
7. **CORS/CSRF/headers** — CSP (endurecer `unsafe-inline`, INFRA-NEW-7), COOP/CORP (✅), clickjacking.
8. **MCP / capability tokens** — enforcement de scope (incl. gate del comodín `*`, ✅), expiración obligatoria, binding a tenant, auditoría de uso.
9. **DoS** — topes de paginación, complejidad de queries (N+1), rate limits por endpoint sensible.
10. **Dependencias** — CVEs (pip-audit/npm audit/trivy) con política de remediación.

**DoD A2:** reporte `docs/audit/SECURITY_REVIEW_<fecha>.md` con cada hallazgo (severidad + CWE + archivo:línea) y, por cada uno, **fix mergeado** o **riesgo aceptado con justificación y dueño** (CTF en `docs/ctf/`). Re-ejecutable: el skill `/security-review` corre sobre cada PR.

### A3 · Auditoría de corrección / R-CODE (por app) — *Fase 1*
Checklist aplicado app por app (las 38), priorizando las de dinero/contables:
- **R-CODE-4 (Decimal):** 0 `float(`/`FloatField`/`Number()*Number()` en rutas monetarias (incl. fronteras de serializer y MCP).
- **R-CODE-11 (asiento atómico):** toda operación con impacto contable pasa por `generar_asiento_o_fallar` dentro de `@transaction.atomic`; ningún `except` que trague el asiento.
- **Concurrencia:** `select_for_update` en stock, saldos y correlativos; idempotencia de operaciones repetibles.
- **Soft delete (R-CODE-6):** todos los querysets de lectura filtran `activo`/estado; sin hard delete.
- **Migraciones (R-PROC-5):** reversibilidad probada (`migrate` hacia atrás) o documentada.

**DoD A3:** checklist firmado por app + tests que prueban cada invariante crítico (ver Parte B).

### A4 · Deuda técnica y arquitectura — *Fase 1*
- Acoplamiento VE en el núcleo (estado de la extracción l10n), imports circulares (`backend/docs/CIRCULAR_IMPORTS_ANALYSIS.md` al día), capas (lógica en `services`, no en `views`), duplicación.
- Inventario de `TODO/FIXME/XXX`, código muerto, apps stub (`eventos` vacía), `# noqa`/`eslint-disable` con justificación.

**DoD A4:** `docs/tech-debt/` actualizado; cada deuda con CTF fechado (R-PROC-6).

### A5 · Cumplimiento del Plan Maestro — *Fase 1*
Re-verificar la matriz §4.2 (estado real de cada módulo) y los gaps de roadmap; alinear el plan con la realidad.

---

## PARTE B — Arquitectura de tests "cero dudas"

### B0 · Pirámide y convenciones
```
        ▲  E2E (Playwright web + API críticos)        — pocos, alto valor
       ▲▲  Contrato/API (schemathesis + OpenAPI)      — todos los endpoints
      ▲▲▲  Integración/servicio (ORM, @atomic, races) — toda services.py
     ▲▲▲▲  Aislamiento multi-tenant (parametrizado)   — todo modelo tenant
    ▲▲▲▲▲  Unidad + property-based (núcleos puros)     — toda la matemática
```
Convenciones: `factory_boy` para todo modelo (factories tenant-aware en `tests/factories/`); marcadores pytest (`unit`, `integration`, `tenant`, `contract`, `e2e`); `hypothesis` para invariantes; un fixture central de "dos empresas + dos usuarios" para aislamiento.

### B1 · Backend — estructura propuesta
```
backend/
├── tests/
│   ├── factories/            # factory_boy por modelo (tenant-aware)
│   ├── conftest.py           # fixtures globales: empresa_a/b, user_a/b, api clients
│   ├── unit/                 # PURO, sin BD (cálculo: decimal, lottt, costeo, igtf,
│   │                         #   iva, scoring, aging) + property-based (hypothesis)
│   ├── integration/          # services.py con BD: @atomic rollback, select_for_update,
│   │                         #   R-CODE-11, flujos de dominio
│   ├── tenant/               # test parametrizado de aislamiento R-CODE-1 (1 archivo
│   │                         #   que descubre todos los ViewSets tenant y prueba
│   │                         #   retrieve/update/delete/list cross-tenant)
│   ├── api/                  # por endpoint: matriz authz, paginación, forma de error,
│   │                         #   validación contra esquema OpenAPI
│   └── e2e/                  # flujos críticos extremo a extremo (API)
│   tests_eval/               # (se mantiene) eval suite de agentes
```
Piezas clave:
- **Aislamiento parametrizado (R-CODE-1):** un único `tests/tenant/test_aislamiento.py` que introspecta el router DRF, y para cada ViewSet tenant ejecuta: usuario de empresa B no puede `GET/PUT/DELETE` un objeto de empresa A (espera 404/403) y `list` nunca incluye objetos de A. **Falla automáticamente si se agrega un ViewSet sin aislamiento.**
- **Property-based (hypothesis)** para invariantes de dinero: `subtotal == Σ líneas`; pagos mixtos suman el total; IGTF solo en divisas; nunca stock negativo; redondeo a 2/4/8 decimales consistente.
- **Race tests:** dos transacciones concurrentes sobre el mismo stock/correlativo → `select_for_update` serializa y no hay doble asignación.
- **Flujos críticos (integration/e2e):**
  1. Venta: cotización→pedido→nota de venta→factura fiscal→descuento de stock→asiento→saldo CxC.
  2. Compra: OC→recepción→factura→CxP→asiento.
  3. Cobranza: gestión→acuerdo→pago de cuota→asiento.
  4. Cambio de divisa: doble registro + asiento + aprobación.
  5. Nómina: período→cálculo LOTTT→proceso→registros (cuando se implemente la orquestación).

### B2 · Frontend — estructura propuesta
```
frontend/src/
├── lib/__tests__/            # decimal, queryKeys, utils (unit)
├── schemas/__tests__/        # zod: parse/format/edge (unit)
├── hooks/__tests__/          # renderHook + MSW (mock API) para use*Form, useQuery
├── components/__tests__/     # Testing Library: ModalPago, tablas, forms + a11y
└── e2e/                      # Playwright contra backend semilla
```
Piezas clave:
- **MSW (Mock Service Worker)** para simular el API en tests de hooks/componentes (sin red).
- **Contrato:** `openapi-typescript` genera tipos desde el esquema del backend; un check de CI **falla si el frontend y el backend divergen**.
- **E2E Playwright:** los mismos flujos críticos del backend, desde la UI, contra un backend con datos semilla.
- Cobertura por capa con piso por carpeta (servicios y hooks ≥ 85%).

### B3 · Gates de CI (la garantía se vuelve automática)
Ampliar `.github/workflows/ci.yml` con jobs (bloqueantes salvo los marcados nightly):
- `static-security`: bandit + semgrep (+ eslint-security).
- `types`: mypy (backend) — `tsc` ya está.
- `deps`: pip-audit + npm audit + trivy (imágenes) — escalar a bloqueante en High/Critical.
- `contract`: generar OpenAPI + drift-check + schemathesis.
- `coverage`: ramp 65→80→90 backend / 56→70→80 frontend + **diff-cover ≥95** (bloquea PRs que bajen cobertura del código nuevo).
- `mutation` (nightly): mutmut sobre módulos críticos, reporte de score.
- `e2e` (PR o nightly): Playwright.
- Pre-commit espejando lo barato (ruff, bandit, gitleaks, eslint).
- **Branch protection** de `main`: estos checks como requeridos.

### B4 · Ramp de cobertura (realista, sin romper)
La cobertura sube por **ratchet** (nunca baja) y por **diff-coverage** (todo PR nuevo ≥95%):
1. Fijar el piso actual + diff-cover ≥95% (efecto inmediato: nada nuevo sin test).
2. Backfill por app priorizada (dinero/contable primero) hasta 80%, luego 90%.
3. Mutation testing valida que los tests **detectan regresiones**, no solo "tocan líneas".

---

## Fases, esfuerzo y orden

| Fase | Contenido | Esfuerzo | DoD |
|---|---|---|---|
| **0 · Tooling + mapa** | A0, A1, B3 (jobs no-bloqueantes), `factory_boy`/`conftest` base, diff-cover activado | 1 sem | herramientas en CI; matrices A1; diff-cover bloqueante |
| **1 · Seguridad** | A2 + A3 + A4 + fixes; `/security-review` integrado | 2–3 sem | reporte de seguridad sin High/Critical abiertos; CTFs para lo aceptado |
| **2 · Cimientos de test** | B1/B2 estructura, aislamiento parametrizado, contrato OpenAPI, harness de races | 2 sem | aislamiento R-CODE-1 cubre todos los ViewSets; contract-drift en CI |
| **3 · Backfill** | tests unidad+integración+property por app hasta 80→90% | 4–6 sem | cobertura objetivo + mutation ≥80% en críticos |
| **4 · E2E + frontend** | Playwright, MSW, hooks/componentes, FE→80% | 2–3 sem | flujos críticos E2E verdes |
| **5 · Endurecer gates** | subir thresholds a definitivos, jobs bloqueantes, branch protection | continuo | "cero dudas" automatizado en cada PR |

**Camino crítico recomendado:** Fase 0 (1 sem) → Fase 1 seguridad (lo que más reduce riesgo) → Fase 2 cimientos (el aislamiento parametrizado y el diff-cover son los de mayor ROI: blindan el futuro) → backfill incremental.

---

## Quick wins inmediatos (se pueden hacer ya, en días)
1. **diff-coverage ≥95% en CI** + `factory_boy`/`conftest` base → ningún código nuevo entra sin test.
2. **Test de aislamiento multi-tenant parametrizado** → blinda R-CODE-1 para siempre.
3. **bandit + semgrep + pip-audit/trivy** como jobs CI → seguridad estática continua.
4. **Tests de integración del código nuevo de Ola 5** (orquestaciones ORM de nómina/manufactura) → cierra el hueco que dejé documentado.
5. **`/security-review`** sobre el último merge (#6) → segundo par de ojos adversarial.

> Este documento es el plan; su ejecución se rastrea como ítems (`TEST-*`, `SEC-*`) con CI verde por fase, igual que el plan de auditoría anterior.
