# Estado de ejecución — Plan "Cero Dudas" (auditoría + testing)

> Seguimiento de [`docs/PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md`](../PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md).
> Cada ítem se cierra con **CI verde** y bajo el [gate de cierre](../DEFINITION_OF_DONE.md).
>
> **Última evaluación:** 2026-06-09 (auditoría ejecutada: Postgres real `omni-erp-db-1` + venv,
> gates corridos uno por uno, no solo lectura del doc).
> **Rama de trabajo:** `claude/cero-dudas-reanudar`. Anterior: `claude/gallant-sagan-I1nRI` (PR #26, ya mergeado).

## Veredicto honesto

El plan está **parcialmente implementado**: **Fases 0–1 cerradas y verificadas**, Fase 2 ~70%, y
la **Fase 3 arrancó de verdad** (mutation testing dejó de ser un no-op y ahora mide baselines
reales por módulo). El criterio de "cero dudas" (cobertura 90/80, mutation ≥80%, E2E, gates
finales bloqueantes) **todavía NO se cumple**. **No se debe afirmar "100% / cero dudas" aún.**

### Verificación 2026-06-09 (ejecutada en este entorno)

Postgres real (contenedor `omni-erp-db-1`, puerto 5434) + Python 3.11/Django 5.2.15:
- Build verde (`check`, `makemigrations --check`, `mapa_superficie --check`). ✅
- ruff (bugs E9/F63/F7/F82/F823/F811) verde sobre `apps/ config/ tests/ tests_api/`. ✅
- Suite completa `tests tests_api/` con `-n auto`: **2293 passed, 9 skipped, cobertura 71.08%**. ✅
- **Gate rojo detectado y corregido:** `test_score_monotono_en_cada_entrada` fallaba de forma
  intermitente. No es un bug — la propiedad es estrictamente monótona y no admite contraejemplo;
  era un `DeadlineExceeded` de Hypothesis (el `deadline` de 200 ms mide tiempo de **pared**, que
  bajo `-n auto` se excede al competir por CPU). Cura idiomática: perfil Hypothesis `ci` con
  `deadline=None` en un `backend/conftest.py` raíz → aplica a todos los property tests.
- *Nota de entorno (Windows):* `bandit`/`semgrep` no instalados localmente y `mypy` crashea por un
  bug de encoding cp1252 al leer su config; en CI (Linux) corren bien y los cambios de esta sesión
  son **solo tests + conftest de test** (no tocan código de apps bajo su scope).

### Verificación 2026-06-07 (ejecutada en este entorno)

Se levantó Postgres + venv y se corrieron los gates de verdad:
- Build verde (`check`, `makemigrations --check`, `mapa_superficie --check`). ✅
- ruff (bugs) / bandit (MEDIUM+) / semgrep (0 findings/616 archivos) / mypy (módulos de dinero). ✅
- Suite: **2134 passed, 8 skipped, cobertura 69.13%**. ✅
- **pip-audit detectó 5 CVEs en Django 5.2.14** (PYSEC-2026-197..201) → corregido a **5.2.15**.

### Los 8 criterios de cierre (estado medido)

| # | Criterio | Estado | Medido |
|---|---|---|---|
| 1 | 0 High/Critical SAST/deps | 🟢 casi | bandit/semgrep/mypy/pip-audit verde; trivy/eslint-security aún no bloqueantes |
| 2 | Cob. back ≥90 / front ≥80 / diff ≥95 | 🔴 | back **71.08%** (ratchet 70), front **~55%**; diff-cover **ya 95%** |
| 3 | Mutation ≥80% críticos | 🟡 | fiscal 46%, nómina 64%, cxc_scoring 70%, cxc_aging 52% (antes: no-op) |
| 4 | Aislamiento multi-tenant | 🟢 | guard parametrizado ~99 ViewSets + comportamiento |
| 5 | Authz + contrato por endpoint | 🟡 | guard authz ✅; schemathesis no-bloqueante |
| 6 | E2E flujos críticos | 🔴 | solo login smoke |
| 7 | mypy dinero + tsc | 🟢 | mypy bloqueante verde; `tsc -b` verde |
| 8 | Revisión seguridad adversarial | 🟢 | SECURITY_REVIEW + `/security-review` |

### Avance sesión 2026-06-09 (rama `claude/cero-dudas-reanudar`)
- **Gate flaky corregido (bloqueante real):** nuevo `backend/conftest.py` raíz registra/carga el
  perfil Hypothesis `ci` (`deadline=None`, suprime `HealthCheck.too_slow`). Elimina el
  `DeadlineExceeded` intermitente de `test_score_monotono_en_cada_entrada` bajo `-n auto`. Aplica a
  **todos** los property tests (`tests/` y `tests_api/`).
- **Backfill finanzas (COV/finanzas):** `tests_api/test_finanzas_views_cobertura.py` — 20 tests de
  API sobre los ViewSets de dinero ejercitando ramas de visibilidad multi-tenant, acciones
  (`monedas/activas`, `cajas/tipo-caja-choices`, `cajas/{id}/movimientos-caja-banco`,
  `cuentas-bancarias/{id}/movimientos-cuenta-bancaria`, `metodos-pago/buscar_reutilizar`) y
  aislamiento cross-tenant (B no ve objetos privados de A; ambas ven la tasa BCV global).
  **`finanzas/views.py` 38.9%→52.6%**, `serializers.py` 46.1%→48.9%.
- **Cobertura total:** 70.53%→**71.08%**; ratchet **69→70** en `pytest.ini`.
- *Pendiente inmediato (siguiente PR focal):* auth_views + mcp_server (tarea #3), ventas/compras
  por API (tarea #4), seguir subiendo el ratchet 70→75→…→90.

### Avance sesión 2026-06-07 (rama `claude/gallant-sagan-I1nRI`, PR #26)
- **Mutation testing reparado:** `mutmut` estaba roto (su pin permitía `junit-xml` 1.8 sin
  `to_xml_report_string` → fallaba al arrancar; el nightly `mutmut run || true` era un no-op
  silencioso). Fijado `junit-xml==1.9`. El nightly pasó a **matrix por módulo** (mutmut usa un
  runner por corrida) con runners unit puros. **Baselines reales:** fiscal 46%, nómina/calculo_lottt
  63.9%, cxc_scoring 70%, cxc_aging 52.3%.
- **Backfill:** `nomina/services.py` 0%→100% (orquestación LOTTT, hueco documentado del plan);
  helpers puros de `contabilidad/services.py`; property-based de aging/scoring CxC; race test de
  abonos CxC (`select_for_update`, completa el pendiente CxC/CxP de TEST-4).
- **Gates:** diff-cover **90→95** (objetivo definitivo). Fix de seguridad **Django 5.2.15** (5 CVEs).
- **Runners de cálculo rápidos creados** (prerequisito de mutación): `test_fiscal_calculos.py`,
  `test_cxc_calculos.py`, `test_nomina_orquestacion.py`, `test_contabilidad_helpers.py`.

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
| **0 · Tooling + mapa** | herramientas en CI, matrices A1, diff-cover | 🟢 **CERRADA** (2026-06-03) | bandit/semgrep(+reglas Omni)/ruff/mypy/pip-audit/npm audit/trivy/gitleaks + **contract (OpenAPI+schemathesis)** + **mutmut nightly** + factory_boy/hypothesis/xdist; **3 matrices A1** con columnas; diff-cover bloqueante. Único diferimiento (`eslint-plugin-security`) formalizado en **CTF-006** (frontend pausado) → DoD cumplida. |
| **1 · Seguridad** | reporte sin High/Critical abiertos, CTFs | 🟢 **CERRADA** (2026-06-03) | **A2-1** `SECURITY_REVIEW_2026-06-02.md` (0 High/Medium de seguridad abiertos); **A3** checklist R-CODE; **A4** inventario; BUG-1/DUP-1/DUP-2 corregidos; **CTF-005** para lo aceptado. |
| **2 · Cimientos de test** | aislamiento parametrizado, contract-drift | 🟡 iniciada | ✅ TEST-1 (aislamiento auto-descubierto), **TEST-2 (estructura `tests/` + aislamiento de comportamiento parametrizado)**, TEST-3 (property), TEST-4 (race), contract en CI. *Falta:* migrar el resto de `tests_api/` por capas, más flujos (TEST-5). |
| **3 · Backfill** | cobertura 90% + mutation ≥80% | 🟡 en curso | cobertura backend **71.08%** (ratchet 70), frontend ~55%; backfill de finanzas/views (38.9→52.6%); **mutation matrix real** con baselines (fiscal 46/nómina 64/cxc_scoring 70/cxc_aging 52) — falta subir a 80 y cobertura a 90 |
| **4 · E2E + frontend** | flujos E2E verdes | 🔴 falta | sin Playwright (solo login smoke); FE en ~55% |
| **5 · Endurecer gates** | jobs bloqueantes + branch protection | 🟡 en curso | bloqueantes: ruff, semgrep Omni, **bandit**, **mypy dinero**, **pip-audit**, **npm critical**, **diff-cover 95**. *Falta:* trivy/schemathesis/E2E bloqueantes, branch protection (requiere permisos del owner) |

Leyenda: 🟢 hecho · 🟡 parcial · 🔴 pendiente.

> **Fases 0 y 1 CERRADAS al 2026-06-03.** Próximo según plan del owner: paréntesis de
> despliegue (Railway + logs del servidor) y luego **Fase 2** en adelante.

---

## Backlog priorizado (por ROI, cada uno = 1 PR con gate)

### Quick wins verificables (horas–días)
- **TEST-1 — Aislamiento multi-tenant auto-descubierto (máximo ROI). ✅ HECHO.**
  `tests_api/test_aislamiento_cobertura.py` introspecta el URLconf y verifica que los ~99
  ViewSets sobre modelos con FK a `Empresa` sobreescriben `get_queryset`; **falla solo si se
  añade un ViewSet sin aislamiento**. Blinda R-CODE-1 para siempre. Verificado local (99
  passed, 1 skip por allowlist). *Pendiente complementario:* variante de comportamiento
  (cross-tenant 404/403) cuando se construya la estructura `tests/` (TEST-2).
- **A1-3 — Tercera matriz `MAPA_MCP_CELERY_COMMANDS.md`. ✅ HECHO.** `mapa_superficie` ahora
  introspecta y genera 17 tools MCP + 13 tareas Celery + 10 management commands; incluida en
  el `--check` bloqueante de CI. *Pendiente:* columnas extra en las dos matrices existentes
  (`test_authz`, `en_openapi`, `unique_together`, `test_aislamiento`).
- **A4-1 — `docs/tech-debt/INVENTORY.md`. ✅ HECHO.** Inventario con 3 TODO de frontend
  (verificados), deuda arquitectónica (§4.3), deuda de tooling y enlaces a auditorías.
- **A5-1 — Corregir §4.2 del Plan Maestro. ✅ HECHO.** Eliminadas apps fantasma
  (`logistica_transporte`, `flota`, `control_calidad`), añadidas `gestion_aprobaciones`/
  `localizacion`, corregido `vzla_localizacion`→`localizacion_ve` (líneas 293, 359, 369).
- **A2-1 — Consolidar** `AUDITORIA_2026-06-02.md` → `docs/audit/SECURITY_REVIEW_2026-06-02.md`
  con formato DoD A2 (severidad + CWE + archivo:línea + estado).

### Seguridad residual (verificar y, si procede, fijar)
- **SEC-1 — empresa de trabajo del asistente IA. ✅ HECHO.** Decisión del owner: el asistente
  opera sobre la **empresa activa** que envía el cliente (validada contra `get_empresas_visible`,
  con fallback a la primera visible); el usuario puede **cambiar de empresa** sólo a otra sobre
  la que tenga permiso. Implementado en `apps/agentes/api/chat.py` con un contexto de empresa
  de trabajo + tools `listar_empresas`/`usar_empresa`; el endpoint rechaza con **403** un
  `empresa_id` no permitido. Se eliminó el uso de `user.empresa` y un **`str(e)` filtrado al
  cliente** (R-CODE-8). 6 tests (`test_chat_empresa_sec1.py`), verificados.
- **SEC-2 — COOP/CORP headers. ✅ YA PRESENTE (verificado).** Ambos nginx
  (`frontend/nginx.conf:14-15`, `infra/nginx/nginx.prod.conf:45-46`) ya tienen
  `Cross-Origin-Opener-Policy` y `-Resource-Policy` (`same-origin`). El assessment estaba
  desactualizado. *(Menor: `nginx.prod.conf:26` tiene un `TODO` de `server_name` de despliegue.)*
- **SEC-3 — CSP**: endurecer `script-src 'unsafe-inline'` (Report-Only + nonces). Requiere
  nonces para MUI/emotion — diferido (riesgo de romper estilos si se hace a ciegas).

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
- **TEST-2 — estructura `backend/tests/` + aislamiento de comportamiento. ✅ HECHO (inicial).**
  Creada la estructura por capas `backend/tests/{factories,unit,integration,tenant,api,e2e}`
  con `conftest.py` sobre `factory_boy` (dos empresas + dos usuarios) y factories tenant-aware
  (Empresa/Moneda/Usuarios); cableada en `pytest.ini` y en el job de CI. `tenant/test_aislamiento_
  comportamiento.py`: tabla declarativa `CASES` (19 modelos) que verifica contra la API real que
  A no ve/edita/borra objetos de B (list, retrieve→404, patch→404 sin mutación, **delete bloqueado**) —
  complementa el guard estructural [TEST-1]. Reemplaza los 3 tests de aislamiento dispersos
  (`base`/`modulos`/`multimodulo`) sin perder cobertura (68.30%, 1072 tests verdes). *Pendiente:*
  migrar el resto de `tests_api/` por capas; ampliar property-based (TEST-3) y races (TEST-4).
- **TEST-3 — property-based con `hypothesis`. ✅ HECHO (inicial).** `test_property_fiscal.py`:
  invariantes de IVA/IGTF (sumas exactas, no-negatividad, redondeo 2 decimales, aplicabilidad
  IGTF) sobre ~1300 casos generados. *Ampliar:* aging, scoring, stock, pagos mixtos.
- **TEST-4 — race tests (`select_for_update`). 🟡 EN CURSO.** ✅ `test_inventario_concurrencia.py`
  (reserva de stock: no overselling, verificado) + el existente `test_fiscal_concurrencia.py`
  (correlativos). *Pendiente:* saldos CxC/CxP.
- **TEST-5 — integración de flujos críticos. 🟡 EN CURSO.** ✅ Compra: el ciclo
  OC→recepción→factura→CxP→asiento ya estaba cubierto (`tests_api/test_m6_compras.py`);
  se agregó la invariante que faltaba — **atomicidad a nivel de flujo**
  (`tests/integration/test_compras_atomicidad.py`): con `contabilidad_activa` y sin mapeo,
  `registrar_recepcion`/`registrar_factura_compra` fallan duro y **revierten todo**
  (recepción, movimiento, stock, CxP), complementando `test_rcode11_centralizado` (helper con
  mocks). ✅ Cobranza: `tests/integration/test_cobranza_atomicidad.py` cubre el endpoint
  `cxc` acuerdos `registrar-pago` (antes **sin test**): con `contabilidad_activa` y sin mapeo
  `PAGO_CXC` responde 422 y **revierte todo** (sin `finanzas.Pago`, cuota intacta, acuerdo no
  auto-completado) + camino feliz con mapeo. ✅ Manufactura:
  `tests/integration/test_manufactura_atomicidad.py` — `consumir_materiales_orden` con BOM de 2
  componentes (uno sin stock) lanza `StockInsuficienteError` y **revierte multi-escritura** (sin
  ConsumoMaterial, sin descuento del componente que sí alcanzaba, orden sigue `pendiente`);
  complementa `test_manufactura_orden_integracion` (camino feliz). **TEST-5 cubre compra, cobranza
  y manufactura.** *Pendiente general de Fase 2:* migrar el resto de `tests_api/` por capas.
- **TEST-6** — frontend: MSW (instalado, sin usar), `openapi-typescript` + drift, Playwright E2E,
  pisos de cobertura por carpeta.

### Backfill de cobertura (semanas, por ratchet)
- **COV-1** — subir `--cov-fail-under` por escalones conforme entra backfill (backend). Estado: **70**
  (medido 71.08% al 2026-06-09); siguientes escalones 75→85→90.
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
