# Handoff — Plan "Cero Dudas" (estado al 2026-06-07)

> ⚠️ **ARCHIVADO (2026-06-10, auditoría integral).** Este handoff quedó superado en 48 h:
> decía cobertura 71.08% y "Fase 3 arrancada"; al 2026-06-09 la Fase 3 cerró con **93.25%**.
> El estado vigente vive en [`docs/audit/ESTADO_PLAN_CERO_DUDAS.md`](../audit/ESTADO_PLAN_CERO_DUDAS.md).
> Sigue siendo útil como referencia de: §1 (setup del entorno), §4.3 (mutation testing local),
> §5 (bloqueos: branch protection del owner) y §6 (convenciones de test).

> Documento para **continuar el plan en un entorno estable**. Resume el estado real
> (verificado ejecutando los gates), lo hecho, lo pendiente y **cómo completarlo paso a paso**.
>
> - Rama: `claude/gallant-sagan-I1nRI` · PR: **#26** (draft, base `develop`) — **ya mergeado**.
> - **Continuación 2026-06-09** en `claude/cero-dudas-reanudar`: fix de gate flaky (perfil
>   Hypothesis `deadline=None` en `backend/conftest.py`) + backfill de `finanzas/views` (38.9→52.6%);
>   cobertura total 70.53→**71.08%**, ratchet **69→70**. Detalle en el seguimiento vivo.
> - Fuente de verdad del plan: [`docs/PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md`](../PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md).
> - Seguimiento vivo: [`docs/audit/ESTADO_PLAN_CERO_DUDAS.md`](ESTADO_PLAN_CERO_DUDAS.md).

---

## 0. TL;DR — dónde estamos

| Métrica | Inicio sesión | Ahora | Objetivo |
|---|---|---|---|
| Cobertura backend | 68.69% | **71.08%** (ratchet 70, 2026-06-09) | 90% |
| Cobertura frontend | ~55% | ~55% | 80% |
| diff-cover (PR) | 90% | **95%** ✅ | 95% |
| Mutation (críticos) | **no-op (roto)** | matrix real: fiscal 46 / nómina 64 / cxc_scoring 70 / cxc_aging 52 | ≥80% |
| Suite backend | 2105 passed | **2293 passed, 9 skipped** (06-09, 0 flaky) | verde |
| SAST/deps (bandit/semgrep/mypy/pip-audit) | verde | **verde** (Django 5.2.15) | 0 High/Crit |

**Veredicto:** Fases 0–1 cerradas y verificadas; Fase 2 ~70%; **Fase 3 arrancada** (mutation real);
Fases 4–5 pendientes. **"Cero dudas" NO alcanzado aún** — es trabajo de varias semanas.

---

## 1. Cómo levantar un entorno estable para continuar

El sandbox usado tenía **Postgres inestable** (se caía cada ~10–15 min) y conflictos de
instalación (`PyJWT` de Debian, `mutmut`/`glob2`). En un entorno estable:

```bash
# Postgres (servicio persistente, no efímero) con la BD/usuario de CI:
#   DB=omni_erp  USER=omni_erp  PASS=omni_erp_ci  (o ajusta env)

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # si falla mutmut/glob2, ver §5.3
export DJANGO_ENV=dev SECRET_KEY=dummy \
  DB_HOST=localhost DB_PORT=5432 DB_NAME=omni_erp DB_USER=omni_erp DB_PASSWORD=omni_erp_ci \
  REDIS_URL=redis://localhost:6379/0

# Gate de cierre (Definition of Done):
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py mapa_superficie --check
python -m pytest tests tests_api/ -n auto        # suite + cobertura (ratchet 69)
ruff check apps/ config/ --select E9,F63,F7,F82,F823,F811
bandit -r apps/ config/ -c .bandit.yaml --severity-level medium
mypy apps/contabilidad apps/finanzas apps/nomina apps/manufactura
semgrep --config p/python --config p/django --config ../.semgrep.yml --severity ERROR --error apps/ config/
```

---

## 2. Lo que se hizo (sesión 2026-06-07, commits en PR #26)

1. **Auditoría real** ejecutando los gates (no solo lectura del doc). Confirmado: Fases 0–1 sólidas.
2. **`mutmut` reparado** — estaba roto (su pin permitía `junit-xml` 1.8 sin `to_xml_report_string`
   → fallaba al arrancar; el nightly `mutmut run || true` era un **no-op silencioso**). Fijado
   `junit-xml==1.9`. El nightly pasó a **matrix por módulo** (mutmut usa un runner por corrida).
3. **Runners de cálculo rápidos** (prerequisito de mutación + cobertura), sin BD:
   `tests/unit/test_fiscal_calculos.py`, `test_cxc_calculos.py`, `test_cxc_cuotas.py`,
   `test_nomina_orquestacion.py`, `test_contabilidad_helpers.py`,
   `test_personalizacion_dsl_validacion.py`, `test_property_cxc.py`.
4. **Backfill** (módulos a 100%): `nomina/services.py`, `cxc/services/cuotas.py`; helpers de
   `contabilidad/services.py`; `finanzas/services.py`→96%; validador DSL.
5. **Race/property CxC**: `tests/integration/test_cxc_abono_concurrencia.py` (cierra pendiente
   CxC/CxP de TEST-4) + property-based de aging/scoring.
6. **Gates**: `diff-cover` 90→95; ratchet cobertura 67→69; **Django 5.2.15** (5 CVEs PYSEC-2026-197..201).

---

## 3. Estado por criterio de cierre (los 8 del plan)

| # | Criterio | Estado | Qué falta |
|---|---|---|---|
| 1 | 0 High/Crit SAST/deps | 🟢 casi | hacer `trivy` y `eslint-plugin-security` bloqueantes (CTF-006/007) |
| 2 | back ≥90 / front ≥80 / diff ≥95 | 🔴 (diff ✅) | subir cobertura back 69.66→90 y front 55→80 |
| 3 | Mutation ≥80% críticos | 🟡 | subir scores matando sobrevivientes (ver §4.3) |
| 4 | Aislamiento multi-tenant | 🟢 | — |
| 5 | Authz + contrato por endpoint | 🟡 | hacer `schemathesis` bloqueante sin 500 |
| 6 | E2E flujos críticos | 🔴 | Playwright de los 5 flujos (ver §4.4) |
| 7 | mypy dinero + tsc | 🟢 | (opcional) ampliar mypy a más apps |
| 8 | Revisión seguridad adversarial | 🟢 | re-correr `/security-review` por PR |

---

## 4. Pendiente + CÓMO completarlo

### 4.1 Backfill de cobertura backend 69.66% → 90% (lo más grande)

**El fruto fácil de lógica pura ya está hecho.** Lo que resta está en **views / serializers /
servicios ORM**, que requieren tests de **integración con BD + API** (`APIClient`).

**Patrón a seguir** (consistencia con lo ya creado):
- Tests puros sin BD → `backend/tests/unit/` (marcador `unit`), con stubs `SimpleNamespace`.
- Tests con BD/servicios → `backend/tests/integration/` (marcador `integration`).
- Tests de API/authz → `backend/tests/api/` o `tests_api/`, usando fixtures de
  `backend/tests/conftest.py` (`empresa_a/b`, `user_a/b`, `client_a/b`).
- **Identificar objetivos**: correr la suite y ordenar por líneas sin cubrir:
  ```bash
  python -m pytest tests tests_api/ -n auto    # genera el reporte term-missing
  # o parsear coverage.xml por archivo
  ```

**Cola priorizada (mayor ganancia, módulos de dinero primero)** — % y stmts sin cubrir medidos:

| Archivo | Cobertura | Stmts sin cubrir | Tipo de test |
|---|---|---|---|
| `apps/finanzas/views.py` | 39% | ~374 | API (cajas, sesiones, tasas) |
| `apps/finanzas/serializers.py` | 46% | ~356 | API + validación |
| `apps/finanzas/models.py` | 65% | ~278 | métodos de modelo (caja: `realizar_cierre`, `conciliar`, `abrir/cerrar_sesion`) con BD |
| `apps/ventas/views.py` | 46% | ~231 | API (flujo de venta) |
| `apps/core/mcp_server.py` | 45% | ~202 | tools MCP + scope |
| `apps/integration_hub/services/sync_engine.py` | 0% | ~166 | integración con mocks de connector |
| `apps/servicio_cliente/views.py` | 41% | ~131 | API |
| `apps/control_asistencia/views.py` | 41% | ~127 | API |
| `apps/core/auth_views.py` | 55% | ~123 | API (JWT login/refresh/logout) |
| `apps/cuentas_por_cobrar/services_cartera_provider.py` | 0% | ~55 | mock del connector Odoo |

**Procedimiento por módulo**: escribir tests → `python -m pytest <archivo_test> --cov=apps.<mod> --cov-report=term-missing` → cerrar ramas → cuando suba el total, **subir el ratchet** en `pytest.ini` (`--cov-fail-under`) por escalones (69→72→75→80→85→90) para bloquear regresión.

### 4.2 Frontend 55% → 80% + (Fase 4)

- Está pausado (CTF-006). Infra ya instalada: `vitest`, `@testing-library/*`, `msw`, `openapi-typescript`.
- Subir pisos en `frontend/vite.config.ts` (`thresholds`) por escalones conforme entren tests.
- Tests de hooks/`use*Form` con **MSW** (mock API), componentes (ModalPago, tablas) con Testing Library.
- Reactivar `eslint-plugin-security` (cerrar CTF-006).

### 4.3 Mutation ≥80% (Fase 3) — matrix ya cableado

El nightly corre un **matrix por módulo** (`.github/workflows/nightly.yml`). Para correr local:

```bash
cd backend && export PATH=.venv/bin:$PATH   # que `python` sea el del venv
mutmut run --paths-to-mutate="apps/fiscal/services.py" \
  --runner="python -m pytest tests/unit/test_fiscal_calculos.py -x -q --no-cov -p no:cacheprovider"
mutmut results            # lista sobrevivientes
mutmut show <id>          # ver el mutante concreto
```

**Para subir el score**: por cada mutante 🙁 *survived*, agregar una aserción al runner que
distinga ese cambio (valor exacto de la rama). Repetir hasta ≥80%. Baselines actuales:
fiscal 46% (sobreviven ramas con BD y constantes), nómina/calculo_lottt 64%, cxc_scoring 70%,
cxc_aging 52% (sobreviven `from_omni`/`from_hub_dict`, que necesitan runner con esos caminos).
**Nota:** los `services.py` de orquestación ORM no son buenos objetivos de mutación (lentos, bajo
valor); enfocarse en archivos de **cálculo puro**.

### 4.4 E2E Playwright (Fase 4)

- Hoy solo `frontend/e2e/login.smoke.spec.ts`; el job `e2e` en CI es `continue-on-error`.
- Implementar los 5 flujos del plan (venta, compra, cobranza, cambio de divisa, nómina) contra
  backend con datos semilla, y luego escalar el job a bloqueante.

### 4.5 Endurecer gates finales (Fase 5)

- En `.github/workflows/ci.yml`: quitar `continue-on-error`/`|| true` de **trivy** y **schemathesis**
  cuando estén limpios; escalar `npm audit` a `--audit-level=high` al cerrar CTF-007.
- **`schemathesis`**: subir `--hypothesis-max-examples`, exigir `not_a_server_error` sin 500.

---

## 5. Bloqueos y notas operativas

### 5.1 🔒 Branch protection (requiere al OWNER)
Configurar en GitHub → Settings → Branches → regla para `main` (y `develop`) exigiendo como
checks requeridos: `Backend`, `Frontend`, `Static analysis`, `Security scan`, `Contract` (cuando
sea bloqueante), `diff-cover`. **No lo puede hacer un agente** — es permiso de administrador.

### 5.2 ⚠️ Inestabilidad de Postgres (entorno sandbox)
El PG efímero se caía periódicamente; cada caída obliga a `service postgresql start` y ralentiza
los tests con BD. En un entorno estable esto desaparece y el backfill de integración rinde mucho más.

### 5.3 Instalación de `mutmut` (si falla)
- `mutmut==2.5.1` arrastra `glob2`, cuyo wheel no compila con setuptools modernos en algunos
  entornos. En un venv limpio (no el setuptools de Debian) compila bien.
- En runtime exige `junit-xml==1.9` (ya fijado en `requirements-dev.txt`); con 1.8 falla al importar.
- Alternativa si `mutmut` sigue dando problemas: evaluar **`cosmic-ray`** (soporta `test-command`
  por módulo de forma nativa, encaja mejor con el matrix por módulo).

---

## 6. Convenciones establecidas (seguirlas para consistencia)

- Estructura `backend/tests/{unit,integration,tenant,api,e2e}` con `conftest.py` central
  (`empresa_a/b`, `user_a/b`, `client_a/b`) sobre `factory_boy`.
- Marcadores pytest: `unit` (sin BD), `integration` (BD/servicios), `tenant`, `contract`, `e2e`.
- Tests puros con `SimpleNamespace` como stubs (ver `test_nomina_orquestacion.py`,
  `test_contabilidad_helpers.py`).
- Dinero siempre `Decimal`; aserciones sobre el **valor exacto** (no solo "no explota") para que
  sirvan también de runner de mutación.
- Commits en español, imperativo; PRs en draft (el humano marca "ready").
- Subir el ratchet de cobertura por escalones, nunca bajarlo.

---

## 7. Próximos pasos sugeridos (orden recomendado)

1. **finanzas** (views+serializers+models) — mayor ganancia de cobertura y módulo de dinero.
2. **core/auth_views** + **mcp_server** — seguridad/authz, alto valor.
3. **ventas/compras** flujos por API (integración).
4. Subir ratchet 69→75→80→85→90 conforme entra cada bloque.
5. Mutation: matar sobrevivientes de fiscal/nómina/cxc hasta ≥80%.
6. Frontend a 80% + E2E Playwright (Fase 4).
7. Gates finales bloqueantes (trivy/schemathesis/e2e) + **branch protection (owner)**.
