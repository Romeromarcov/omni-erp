# Registro de decisiones y estado — sesión 2026-06-12 (owner + agente)

> Persistencia anti-pérdida-de-contexto: todo lo decidido y el estado exacto de la ejecución.
> Fuente: conversación owner (Marco) ↔ agente, sesión de Claude Code del 2026-06-12.

## 1. Hechos consumados hoy

- **Release a producción** (#100, método MERGE): 20 PRs — nómina LOTTT completa (+UI), manufactura 1.I, POS mostrador, UIs compras/CxP/contabilidad/tesorería, cambio de divisa atómico (cierra CTF-013), apps nativas Windows/Android, seguridad S1+P1, PWA offline nivel 1, 13+ bugs, backups con restore test. Prod verificada sana (health 200 backend y frontend).
- **Gate de diff-cover reparado y endurecido** (#101): el `if: pull_request` + trigger filtrado a base=main hacían que el gate ≥95% NUNCA corriera para PRs a develop; primera medición real dio 91%. Se cubrieron las 119 líneas con 70 tests reales (3 agentes), el paso corre ahora en TODOS los eventos, y el agregado vs main mide **99%**. Fix determinista del test flaky de rate-limit (reloj de django-ratelimit congelado).
- **#102**: back-merge de ancestría main→develop (0 archivos) para satisfacer "require up-to-date".
- **Post-release a develop**: #97 (Zelle terceros), #98 (UI RRHH/nómina), #99 (gateway LLM con cascada+circuit breaker+consumo), #103 (bugs lote 3 + **CTF-015 cerrado**: transferir-entre-cajas reparado, cantidad>0 en OF, perform_create de sesiones de caja, overrides verificado sin agujero), #104 en CI (**CTF-006 y CTF-007 cerrados**: eslint-plugin-security bloqueante con 47 fixes reales + 17 supresiones justificadas, picomatch saneado vía typescript-eslint 8.61, gate `npm audit --audit-level=high` en CI).
- Owner completó: seeds de staging ✅ · `REFRESH_TOKEN_COOKIE_SAMESITE=None` en prod ✅ · branch protection activa ✅.

## 2. Decisiones del owner (vigentes)

1. **Cadencia de release**: develop→main cuando se acumulen **~15 PRs** con CI verde (no por PR individual). develop→main = método MERGE + autorización humana; PRs a develop = squash "título (#N)" + revisor agente independiente + CI 7/7.
2. **Fases del roadmap: mantener el orden actual** (ola de deuda → 1.G remanente → P2-2/P2-3 → L10n → plataforma de extensión).
3. **Offline nivel 2 es OBLIGATORIO** (no omitible), en su posición actual de la cola.
4. **Directriz de producto: offline-first donde sea posible** — crítico para el contexto venezolano. Toda feature debe responder "¿qué pasa sin conexión?" antes de cerrarse. (Base ya construida: PWA nivel 1, Idempotency-Key para reintentos seguros.)
5. **Backups (P0-9)**: pospuestos por el owner — la infra está completa; solo faltan secrets (runbook `docs/runbooks/RUNBOOK_BACKUPS.md`, ~10 min cuando decida).
6. **Cerrar todos los CTFs y toda la deuda técnica** (mandato 2026-06-12): 013 ✅, 015 ✅, 006/007 en PR #104; quedan 012 (RLS) y 014 (migración tests) — ver §4.
7. **Arquitectura de extensibilidad y fábricas**: ADR-010 y ADR-011 (aceptadas hoy).

## 3. Backlog nuevo registrado hoy

- **Optimización CI**: activar `pytest-xdist` (`-n auto`) en el job Backend (~mitad del tiempo). Hacerlo como PR propio con vigilancia de flakiness de aislamiento. (Pedido del owner.)
- **Bugs lote 4** (hallazgos del revisor de #103 + autor): `CajaUsuarioViewSet.crear_caja_virtual` llama método inexistente (AttributeError latente) · PATCH a sesiones-caja puede "reabrir" vía `estado` writable · carrera de doble apertura concurrente (IntegrityError 500) · `monto=0` cae en guard genérico · transferencias no filtran cajas `activa=False`.
- Doc-sync pendiente: casillas del PLAN_MAESTRO (36 sin marcar pero mayormente hechas) y ESTADO_PLAN_CERO_DUDAS (última eval 06-09; Fases 4-5 ya cerradas hoy).
- Plan cero dudas: **cerrado en sus 5 fases**; los CTF fechados restantes son compromisos, no fases.

## 4. Cola de ejecución (estado al cierre de este registro)

| Ítem | Estado |
|---|---|
| #104 CTF-006/007 | CI corriendo, revisor APROBADO, merge al verde |
| Capa B §6.7/6.8 (pagos parafiscales + libro maestro de caja) | Agente trabajando |
| P2-4 (CACHES Redis cross-worker) + P2-5 (django-csp) | Agente trabajando |
| CTF-012 + rollout RLS (rol no-dueño; 15→~92 tablas; staging) | En cola tras parafiscales (conflictos de migraciones). Activación en PROD = con el owner |
| Bugs lote 4 | En cola tras parafiscales |
| CTF-014 (tests_api→tests/ por capas) | Al final de la ola (mueve archivos que todos tocan) |
| 1.G remanente: comisiones de vendedores · devoluciones/NC en POS · `apps/despacho` · **offline nivel 2 (obligatorio)** | Tras la ola de deuda |
| P2-2 (agentes→Celery) · P2-3 completo (persistir consumo LLM por tenant) | Tras 1.G; prerrequisitos de agentes custom (ADR-010 §5) |
| Fase L10n (§3.7: ADR-007, `apps/localizacion`, puertos, `localizacion_ve`, `Empresa.pais`) | Después; es la base del plugin system |
| Plataforma de extensión + marketplace (ADR-010) · fábricas (ADR-011) | Post-L10n; fábrica de software puede arrancar en modo sombra antes |

**Bucket operativo (no-código, owner)**: migración de datos reales de la distribuidora · datos fiscales reales + primera factura válida + libro SENIAT · capacitación/arranque en paralelo · demo grabada · secrets de backups · revocar el PAT de la sesión zombie del 2026-06-12 (si no se hizo) · opcional: "Allow auto-merge" en GitHub y agregar `Security scan` a los checks requeridos.

## 5. Convenciones operativas del agente (para retomar sin contexto)

- Flujo por PR: rama desde develop → agente worktree (`.env` copiado, venv compartido `backend/.venv`, `TEST_DB_NAME` único, `--cov-fail-under=0` en subsets) → revisor agente independiente → push → CI 7/7 → si `behind`: update branch o merge local de develop → squash-merge.
- Tras `update_pull_request_branch`/merge de develop: regenerar `mapa_superficie` si cambió superficie backend (lección #97) y re-pasar lint de seguridad en frontend nuevo (lección #104/#98).
- Railway webhooks de PR-envs = ruido, sin acción. Timers de background para esperar CI (los webhooks no entregan éxitos).
- El repo local develop debe pullearse antes de crear worktrees (lección: agentes nacidos de develop viejo).

## 6. PAUSA por tokens (2026-06-12 ~23:20 UTC) — estado de reanudación

**La ola de deuda quedó COMPLETA** (#103–#111 mergeados): CTFs 006/007/013/014/015 CERRADOS,
012 al máximo (solo pasos operativos del owner: `docs/runbooks/RUNBOOK_RLS_ROL_APP.md`).
Develop **+12 sobre main** — a ~3 PRs del umbral de release (~15).

**Trabajo en vuelo PAUSADO** (3 agentes 1.G detenidos; su avance quedó commiteado como WIP
en ramas remotas, partiendo todos de base vieja a8b872d → al reanudar: merge develop + verificar):
- `wip/pausa-1g-aa1369958d45398ea` — **comisiones de vendedores** (modelos+API hechos; estaba
  regenerando openapi.json/schema.d.ts por el cambio de superficie).
- `wip/pausa-1g-ad6e34069a13b3aa0` — **devoluciones/NC en POS** (backend+frontend avanzados;
  estaba re-corriendo la suite frontend por flakiness de carga, 5s timeouts).
- `wip/pausa-1g-ac7e3da1ce291013c` — **apps/despacho** (app construida; limpiando un import
  en fiscal/models.py de su diff).

**Cómo reanudar**: por cada rama wip → worktree → merge origin/develop → completar lo que el
WIP note diga → suites por capas (tests/ — ya NO existe tests_api/) → diff-cover ≥95% → PR →
revisor independiente → CI → squash-merge. Luego: **offline nivel 2 (OBLIGATORIO)** → P2-2
(Celery) → P2-3 → fase L10n → plataforma de extensión (ADR-010/011).

**Backlog menor acumulado**: homogeneizar markers de capa (hook `pytest_collection_modifyitems`
por directorio; p24 marker unit vs carpeta integration) · xdist en CI · follow-ups RLS anotados
en CTF-012 · menores de revisores en #103/#106/#107/#108 ya registrados arriba.
