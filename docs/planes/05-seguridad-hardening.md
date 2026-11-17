# Plan 05 — Hardening de seguridad y resiliencia

> Plan de ejecución derivado de una auditoría de seguridad sobre `main` (2026-06-07).
> Aterriza en frentes accionables los hallazgos de la auditoría más las recomendaciones
> adicionales. Alineado a [`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) §2 (R-CODE /
> R-PROC / R-PROD) y al gate de cierre [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md).

| Campo        | Valor                                  |
|--------------|----------------------------------------|
| **Estado**   | EN CURSO — P0-1 (RLS infra ✅, activación bloqueada por [CTF-012](../ctf/CTF-012.md)), P1-1..P1-4/P2-1/P2-5 ✅, P1-7/P2-3/P2-4 parciales; P1-5/P1-6/P2-2/P2-6/P3 abiertos |
| **Fecha**    | 2026-06-07 (estado actualizado 2026-11-17 contra `develop @ ff2bdb6`) |
| **Esfuerzo** | ~3–4 semanas (repartibles en paralelo) |
| **Owner**    | equipo-backend / equipo-agentes / devops |

---

> ⚠️ **Nota cruzada:** este plan es *hardening proactivo*; los hallazgos puntuales de seguridad
> viven en las auditorías (`SECURITY_REVIEW_2026-06-02.md` y `AUDITORIA_INTEGRAL_2026-06-10.md`,
> ambas **cerradas** — sus fixes P0 ya se mergearon; ver [`docs/auditorias/archivo/`](../auditorias/archivo/)
> y la auditoría integral [`AUDITORIA_2026-06-21.md`](../AUDITORIA_2026-06-21.md)).
> "Hallazgos cerrados" ≠ "hardening completo", y viceversa.

## 0. Resumen — estado actual por hallazgo

Leyenda: ✅ implementado · ⚠️ parcial · ❌ falta.

### De tu checklist original

| # | Medida | Estado | Evidencia |
|---|--------|--------|-----------|
| 1 | Row Level Security (PostgreSQL) | ⚠️ | Infra y 124/124 tablas + Connect/Tareas/CxC_Lubrikca con `FORCE ROW LEVEL SECURITY`; activación real pendiente ([CTF-012](../ctf/CTF-012.md) / Plan 06 Fase 2: rol `omni_app` no-dueño) |
| 2 | CORS | ✅ | `django-cors-headers`; prod fail-closed (`settings_prod.py`) |
| 3 | Security headers | ✅ | Django prod (`settings_prod.py`) + nginx con CSP + `django-csp==4.0` enforce (P2-5, #106) |
| 4 | Arquitectura desacoplada / gateway LLM / agnóstica | ✅ | `apps/core/llm_gateway.py` (P2-1, #99): punto único configurable por env; sin `anthropic.Anthropic()` directo fuera del gateway |
| 4b | Fallback a otros modelos si el principal falla | ✅ | Cascada `LLM_MODEL` → `LLM_MODEL_FALLBACK` → reglas deterministas + circuit breaker (P2-1, #99) |
| 5 | Arquitectura orientada a eventos / IA en background | ⚠️ | Celery+Redis+Kafka existen; sugerencias diarias en Beat. Agentes en `apps/agentes/views.py` aún corren síncronos (**P2-2 abierto**) |
| 5b | WebSockets para streaming | ⚠️ | Hay **SSE** en chat (`StreamingHttpResponse`); no hay Django Channels (full-duplex, **P3-3**) |
| 6 | RAG | ❌ | Sin pgvector / embeddings / vector store / retrieval (**P3-2 abierto**) |
| 7 | Frontend comprimido sin source maps | ✅ | Vite sin `build.sourcemap`, bundle minificado, gzip nginx |
| 8 | Rate limiting | ✅ | Nginx (`login 5/m`, `api 60/m`) + `django-ratelimit` en login + DRF throttling global y `EscrituraRateThrottle` (P1-1, #84) |
| 9 | Cache | ⚠️ | `CACHES["default"]` con Redis DB 1 separado de Celery DB 0, fail-closed (`config/caches.py`, P2-4 #106). **Falta** cachear consultas calientes y barrido N+1 |
| 10 | Escalabilidad | ✅ | uvicorn workers, Celery `concurrency=4`, stateless, Docker |
| 11 | Monitoreo | ✅ | Sentry (`send_default_pii=False`), logging estructurado, healthchecks, `RegistroAuditoria` |
| 12 | Sin API keys/secretos en código | ✅ | `SECRET_KEY` obligatorio desde env; todo desde env; `.env` en `.gitignore` |
| 13 | Validación de inputs / anti-inyección | ✅ | ORM parametrizado, Serializers DRF, `RunSQL` literales; frontend Zod + react-hook-form |

### Recomendaciones adicionales (no estaban en la checklist)

| # | Recomendación | Estado |
|---|---------------|--------|
| R1 | `pip-audit` + `npm audit` en CI (escaneo de dependencias) | ✅ ya en `develop` (CI job "Security scan") |
| R2 | Secret scanning (gitleaks/trufflehog) pre-commit + CI | ✅ ya en `develop` (gitleaks en CI) |
| R3 | Throttling DRF global (más allá del login) | ✅ **P1-1 (#84)** — `THROTTLE_RATE_*` + `EscrituraRateThrottle` en endpoints de pago/abono |
| R4 | Rotación/revocación de JWT (blacklist al logout) | ✅ **P1-4 (#84)** — blacklist + rotación verificadas (`tests/api/test_s1_seguridad.py`) |
| R5 | 2FA/MFA para admin/superusuario Omni | ❌ (**P3-1 abierto**) |
| R6 | Política de contraseñas + bloqueo de cuenta (django-axes) | ✅ **P1-3 (#84)** — `django-axes 8.3.1` (10 intentos, 15 min) + `PASSWORD_MIN_LENGTH=12` |
| R7 | Permisos a nivel objeto auditados (no solo filtro de queryset) | ⚠️ (**P1-6 abierto** — pasada IDOR crítica pendiente) |
| R8 | Backups automáticos + prueba de restore de PostgreSQL | ⚠️✅ **P1-7 (#96)** — `backup.yml` + `restore-test.yml` + `RUNBOOK_BACKUPS.md` listos; **falta secret/bucket del owner** |
| R9 | Idempotencia en endpoints de pago/creación (claves idempotentes) | ✅ **P1-2 (#86)** (`apps/core/idempotency.py`, `ClaveIdempotencia`) |
| R10 | Circuit breaker / timeouts en llamadas LLM | ✅ **P2-1 (#99)** (`LLM_TIMEOUT`, `LLM_MAX_RETRIES`, `LLM_CB_UMBRAL`/`VENTANA` en `llm_gateway.py`) |
| R11 | Observabilidad de costos LLM (tokens por tenant) | 🟡 **P2-3 parcial (#99)** — log estructurado `llm_consumo` + hook `registrar_consumo_hook`; **falta persistencia dedicada** |
| R12 | Tracing distribuido (OpenTelemetry) — Celery + Kafka + agentes | ❌ (**P2-6 abierto**) |
| R13 | Auditoría inmutable (`RegistroAuditoria` no editable/borrable) | ⚠️ (**P1-5 abierto** — revocar UPDATE/DELETE al rol de aplicación) |
| R14 | CSP a nivel Django (`django-csp`, nonce por request) | ✅ **P2-5 (#106)** (`django-csp==4.0` enforce; `tests/api/test_p25_csp.py`) |

---

## Prioridades

- **P0 — Crítico.** Riesgo de fuga cross-tenant o de seguridad explotable hoy. Bloquea el próximo hito.
- **P1 — Alto.** Barato + alto impacto, o defensa en profundidad sobre dinero/datos.
- **P2 — Medio.** Resiliencia, deuda de arquitectura IA, control de costos.
- **P3 — Evolutivo.** Mejora incremental según necesidad de producto.

---

## FASE P0 — Crítico (semana 1)

### P0-1 · Row Level Security en PostgreSQL (R-CODE-1) — `❌`
**Por qué:** es el mayor riesgo real. Hoy el aislamiento multi-tenant depende 100% de que
ningún queryset olvide el filtro por empresa. Un solo bug = fuga entre tenants sin red en la BD.

**Tareas:**
1. Identificar tablas con `id_empresa` y definir la estrategia: variable de sesión
   `SET app.current_empresa` por request (middleware) + `CREATE POLICY` por tabla.
2. Middleware que setea `app.current_empresa` / `app.is_superusuario_omni` en la conexión
   tras autenticar (junto a `apps/core/middleware` y `get_empresas_visible()` en
   `apps/core/viewsets.py:229`).
3. Migración(es) que hagan `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + `FORCE` + políticas
   `USING (id_empresa = current_setting('app.current_empresa')::uuid OR current_setting('app.is_superusuario_omni')='1')`.
4. Rol de BD de aplicación **sin** `BYPASSRLS`; rol de migraciones aparte.
5. Tests en `backend/tests/tenant/` que prueben que un usuario del tenant A **no** ve filas
   del tenant B **aunque** se elimine el filtro del queryset (verificación a nivel BD).

**DoD:** RLS activa y forzada en todas las tablas multi-tenant; test de fuga cross-tenant
verde con el filtro de aplicación deshabilitado; sin regresión en `tests/`.
**Esfuerzo:** ~4–6 días. **Owner:** equipo-backend.

#### Estado — `🟡 EN CURSO` (PR `fix/seguridad-hardening`)
**Entregado (infra + piloto):** `apps/core/rls.py` (builders DDL + helpers de runtime),
`signals.py` (default de conexión), `middleware.py` (`RLSContextMiddleware`, resuelve
usuario por sesión/JWT), flag `RLS_ENABLED`, y RLS **forzado** en 7 tablas piloto que
cubren las 3 variantes de columna (`sucursales`, `ventas_pedido/nota_venta/factura_fiscal`,
`finanzas_transaccion_financiera`, `cxc_gestioncobranza/acuerdopago`). 21 tests (aislamiento
a nivel BD con filtro de app ausente, fail-closed, bypass, `WITH CHECK`, streaming, middleware).
Gate verde (2240 passed, cobertura 69.97%). `RLS_ENABLED=False` por defecto.

**Lote 2 (rollout, follow-up 5):** RLS **forzado** en 8 tablas más de inventario / compras /
crm (todas con columna `id_empresa_id`): `inventario_producto`, `inventario_stock_actual`,
`inventario_movimiento_inventario`, `compras_orden_compra`, `compras_recepcion_mercancia`,
`crm_cliente`, `crm_contacto_cliente`, `crm_direccion_cliente`. Una migración RLS por app
(`inventario/0008_rls_lote2_inventario`, `compras/0010_rls_lote2_compras`,
`crm/0009_rls_lote2_crm`) reusando los builders, con `reverse_sql`. 7 tests nuevos a nivel BD
(`tests/tenant/test_rls_lote2.py`) sobre `crm_cliente` y `crm_contacto_cliente`: aislamiento sin
filtro de app, fail-closed, bypass, `WITH CHECK`. `RLS_ENABLED=False` sigue por defecto.

**Lote 3 (CTF-012, rollout completo):** RLS **forzado** en las 107 tablas tenant
restantes → **124/124 tablas con FK a `core.Empresa` cubiertas** (33 migraciones
reversibles `*_rls_lote3_*`, una por app). Variante `null_visible` del builder para
los 11 catálogos compartidos con columna de empresa nullable (`empresa NULL` = fila
global visible por todos, igual que el filtrado de aplicación). Excluidas con razón
en `rls.RLS_EXCLUDED_TABLES`: `empresas` (raíz del tenant) y `fiscal_retencion`
(bi-empresa). Comando idempotente `configurar_rol_rls` (rol `omni_app` no-dueño,
`NOSUPERUSER NOBYPASSRLS`, GRANTs mínimos + default privileges; contraseña solo por
env), soporte `MIGRATIONS_DATABASE_URL` en `entrypoint.sh` y runbook de activación
`docs/runbooks/RUNBOOK_RLS_ROL_APP.md`. Tests: registro 1:1 contra modelos (un
modelo tenant nuevo sin RLS rompe CI), `pg_policies`/`FORCE` parametrizado por
tabla y aislamiento real en tablas representativas (`tests_api/test_rls_rollout.py`,
`tests_api/test_rls_rol_app.py`). `RLS_ENABLED=False` sigue por defecto; la
activación (cambio de rol en staging → prod) la gobierna CTF-012.

**Criterios de rollout / follow-ups (antes de activar en prod):**
1. **Rol de BD dedicado no-dueño** (sin `BYPASSRLS`) para el runtime, con migraciones
   corriendo como dueño. Da fail-closed *natural* a nivel de app sin depender del default
   `bypass='on'` de conexión (hoy fail-open para paths que no pasen por el middleware, p. ej.
   tareas Celery que agregan cross-tenant). Es la forma correcta de cerrar la observación
   MEDIA de la revisión de seguridad. **Bloqueante para `RLS_ENABLED=True` en prod.**
2. **Memoización por request** de `get_empresas_visible(user)` en el middleware (hoy recorre
   subsidiarias en cada request con RLS activo).
3. **Documentar** que con RLS activo el acceso de Django admin requiere `es_superusuario_omni`
   (un `is_superuser` que no lo sea queda acotado por tenant).
4. **Streaming + pooling:** si se habilita `CONN_MAX_AGE`/pgbouncer, fijar el contexto RLS
   dentro del generador SSE (hoy resuelto no-reseteando en `finally` con `CONN_MAX_AGE=0`).
5. ~~Extender RLS al resto de tablas multi-tenant~~ ✅ hecho en el lote 3 (124/124).
   Pendiente menor: política propia para `empresas` y `fiscal_retencion` (excluidas
   documentadas en `rls.RLS_EXCLUDED_TABLES`).

### P0-2 · `pip-audit` + `npm audit` en CI (R1) — `✅ YA HECHO en develop`
Verificado en `.github/workflows/ci.yml` (job **"Security scan (gitleaks + deps audit)"**,
INFRA-NEW-4): `pip-audit -r requirements.txt` **bloqueante** y `npm audit --audit-level=critical`
**bloqueante**. El salto a `--audit-level=high` está fechado en **CTF-007** (un HIGH pendiente).
Nada que hacer aquí salvo cerrar CTF-007 a su tiempo.

### P0-3 · Secret scanning (R2) — `✅ YA HECHO en develop`
Verificado en `.github/workflows/ci.yml`: **gitleaks** (`gitleaks/gitleaks-action@v2`) corre en
CI con `fetch-depth: 0` (historial completo). Mejora opcional pendiente: agregar gitleaks
también como **hook pre-commit** (defensa antes del push). Esfuerzo ~0.25 día.

---

## FASE P1 — Alto (semana 1–2)

### P1-1 · Throttling DRF global (R3, #4) — `✅` (PR #84)
**Por qué:** el rate limit fino solo cubría login. El resto de la API (incluida escritura) necesitaba techo de abuso a nivel aplicación.

**Estado — `🟢 HECHO` (PR #84):** tasas configurables por entorno (`THROTTLE_RATE_*` en `config/settings_base.py`) y `EscrituraRateThrottle` (`apps/core/throttling.py`, `60/min` en métodos no seguros) aplicado a `PagoViewSet`, `AbonoCxCViewSet` y `AbonoCxPViewSet`. Tests en `tests/api/test_s1_seguridad.py`.

### P1-2 · Idempotencia en pagos/creación (R9) — `✅`
**Por qué:** ERP financiero; un doble-submit o reintento de red no puede duplicar un pago o
una factura.

**Tareas:** cabecera `Idempotency-Key` + tabla de claves usadas; aplicar en `apps/ventas`
(pagos, confirmar nota) y `apps/cxc`.
**DoD:** reintento con misma clave devuelve el mismo resultado sin duplicar; tests.
**Esfuerzo:** ~2 días. **Owner:** equipo-backend.

#### Estado — `🟢 HECHO` (PR `feature/p1-2-idempotencia-pagos`)
Mecanismo en `apps/core/idempotency.py` (`@idempotent(scope)` + `IdempotentCreateMixin`)
sobre `ClaveIdempotencia` (unicidad `(empresa, usuario, scope, clave)`, TTL 24h con purga
perezosa, registro "en vuelo" que serializa el doble-submit concurrente vía índice único;
payload distinto → 422; sin cabecera → opt-out). Aplicado a: abono CxC (`abonar` y
`AbonoCxCViewSet.create`), `PagoViewSet.create` (finanzas), `registrar-pago` de acuerdos,
confirmar pedido y conversión nota de venta → factura. Tests en
`tests/api/test_idempotencia.py` + race test con hilos en
`tests/integration/test_idempotencia_concurrencia.py`.

### P1-3 · Bloqueo de cuenta + política de contraseñas (R6) — `✅` (PR #84)
**Por qué:** rate-limit por IP no frena fuerza bruta distribuida ni credential stuffing.

**Estado — `🟢 HECHO` (PR #84):** `django-axes 8.3.1` (`AxesStandaloneBackend`, `AXES_FAILURE_LIMIT=10`, cooloff 15 min configurables por env) con respuesta JSON 429 genérica sin filtrar existencia de usuario en `login_view`/`CustomTokenObtainPairView`, y política de contraseñas reforzada (`PASSWORD_MIN_LENGTH=12` + validadores estándar). Tests en `tests/api/test_s1_seguridad.py`.

### P1-4 · Revocación de JWT al logout (R4) — `✅` (PR #84)
**Por qué:** un token robado debe poder invalidarse; el logout debe revocar de verdad.

**Estado — `🟢 HECHO` (PR #84):** `rest_framework_simplejwt.token_blacklist` + rotación activas (access TTL 15 min), verificadas con test de flujo real logout vía cookie httpOnly → reuso del refresh falla con 401 (`tests/api/test_s1_seguridad.py`).

### P1-5 · Auditoría inmutable (R13) — `⚠️ verificar`
**Por qué:** `RegistroAuditoria` solo sirve si no puede ser editado/borrado por la propia app.

**Tareas:** revocar UPDATE/DELETE sobre la tabla al rol de aplicación (regla append-only a
nivel BD); revisar que ningún ViewSet exponga edición.
**DoD:** intento de UPDATE/DELETE sobre auditoría falla a nivel BD; test.
**Esfuerzo:** ~0.5 día. **Owner:** equipo-backend.

### P1-6 · Permisos a nivel objeto auditados (R7) — `⚠️`
**Por qué:** el filtro de queryset oculta, pero hay que confirmar que no haya IDOR en
`retrieve`/`update`/`delete` por PK directa.

**Tareas:** auditar ViewSets críticos (ventas, cxc, finanzas, compras); test de acceso
cruzado por PK; complementa P0-1.
**DoD:** test IDOR cross-tenant verde en endpoints críticos.
**Esfuerzo:** ~1.5 días. **Owner:** equipo-backend.

### P1-7 · Backups + prueba de restore de PostgreSQL (R8) — `⚠️✅` (PR #96, falta secret owner)
**Por qué:** no asumir que Railway lo cubre; un backup sin restore probado no es un backup.

**Estado — `🟡 INFRA/WORKFLOW HECHOS (PR #96); FALTA OPERATIVO DEL OWNER`:**
- `.github/workflows/backup.yml` (dump diario 06:00 UTC → S3, retención 30 días).
- `.github/workflows/restore-test.yml` (restore semanal automatizado los lunes 07:00 UTC sobre Postgres efímero + validación de ≥50 tablas y antigüedad <48h).
- [`docs/runbooks/RUNBOOK_BACKUPS.md`](../runbooks/RUNBOOK_BACKUPS.md) documentando pasos de configuración y recuperación ante desastres.
- **Pendiente (acción exclusiva del owner):** crear el bucket S3/R2 y cargar los secrets `BACKUP_DB_HOST`, `BACKUP_DB_*`, `BACKUP_S3_*` y `BACKUP_AWS_*` en GitHub Actions para ejecutar la primera corrida real.

---

## FASE P2 — Medio (semana 2–3)

### P2-1 · Gateway LLM agnóstico + fallback multi-modelo + timeouts/circuit breaker (#4, #4b, R10) — `✅` (PR #99)
**Por qué:** unifica agnosticidad de proveedor, failover real entre modelos, timeouts y
control de fallos en un solo componente. Antes `anthropic.Anthropic()` estaba en 6 sitios con
modelos hardcodeados.

**Estado — `🟢 HECHO` (PR #99):**
- `apps/core/llm_gateway.py`: punto único de entrada (`generate()`, `stream()`, `disponible()`), modelos configurables por env (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_MODEL_CHAT`, `LLM_MODEL_ANALISIS`, `LLM_MODEL_FALLBACK`), timeouts/reintentos (`LLM_TIMEOUT`, `LLM_MAX_RETRIES`), cascada principal → alterno → `LLMUnavailable` (con fallback determinista en call sites) y circuit breaker atómico (`LLM_CB_UMBRAL`, `LLM_CB_VENTANA`) sobre `CACHES` compartido.
- Migrados los 6 sitios (`clasificador.py`, `cobranza.py`, `reorden.py`, `personalizacion_agente.py`, `chat.py`, `cxc/agents/cobranza_agent.py`).
- Guard de superficie + 43 tests en `tests/unit/test_llm_gateway.py` (antes `tests_api/test_llm_gateway.py`).

### P2-2 · Mover agentes de las vistas a Celery (#5) — `⚠️` (ABIERTO)
**Por qué:** ya existe la infra (Celery+Redis+Beat); las vistas que llaman agentes en
`apps/agentes/views.py` corren síncronas y bloquean el request.

**Tareas:** convertir acciones de análisis a `.delay()` / `apply_async()`; devolver job id;
exponer estado (poll o vía SSE existente).
**DoD:** análisis de agentes fuera del request HTTP; test de encolado.
**Esfuerzo:** ~2 días. **Owner:** equipo-agentes.

### P2-3 · Observabilidad de costos LLM por tenant (R11) — `🟡 PARCIAL` (hook + logs en PR #99; falta persistencia)
**Por qué:** control de gasto y detección de abuso; encaja con el billing futuro del Plan C.

**Estado actual (PR #99):** `apps/core/llm_gateway.py` emite un log estructurado `llm_consumo` (proveedor, uso, modelo real, empresa, tokens in/out) en cada llamada y expone el punto de extensión `registrar_consumo_hook`.
**Pendiente:** crear tabla dedicada (o extender `RegistroAuditoria` / `saas`) para persistir tokens y costo estimado por tenant + vista/consulta agregada + tests.
**DoD:** consumo histórico por tenant consultable vía API/admin; test de registro persistido.
**Esfuerzo restante:** ~1 día. **Owner:** equipo-agentes.

### P2-4 · `CACHES` de Django con Redis (#9) — `🟡 PARCIAL` (PR #106; falta cacheo consultas/N+1)
**Por qué:** Redis ya está para Celery; falta cachear queries ORM caras y reducir N+1.

**Tareas pendientes:** cachear catálogos/consultas frecuentes usando `CACHES["default"]`; revisar
N+1 con `select_related`/`prefetch_related` en ViewSets de mayor tráfico.
**DoD:** invalidación correcta; sin N+1 en endpoints calientes.
**Esfuerzo restante:** ~1 día. **Owner:** equipo-backend.

#### Estado — `🟡 PARCIAL: CACHES hecho` (PR #106, `feature/p2-4-redis-p2-5-csp`)
`CACHES["default"]` configurado con el backend **nativo** de Django
(`django.core.cache.backends.redis.RedisCache`, sin necesidad del paquete
`django-redis`) vía `config/caches.py`: con `REDIS_URL` usa Redis en una **DB
distinta** de la del broker Celery (`REDIS_CACHE_DB`, default 1 vs. DB 0;
colisión → `ImproperlyConfigured` fail-closed, porque `cache.clear()` hace
`FLUSHDB`), `KEY_PREFIX` por entorno (`CACHE_KEY_PREFIX`, default
`omni:<RAILWAY_ENVIRONMENT|dev>`); sin `REDIS_URL` cae a LocMem (dev local).
**Bajo pytest se fuerza LocMem siempre** (CI exporta `REDIS_URL` sin servicio
Redis en los jobs de pytest; determinismo de throttle/SEC-07/idempotencia).
Los jobs CI con servidor vivo (e2e, contract) ahora levantan un service
`redis:7-alpine` y ejercitan el path real. Con esto, rate-limiting SEC-07,
throttling DRF (P1-1) y el circuit breaker del gateway LLM (P2-1)
comparten estado entre workers en producción. Tests:
`tests/integration/test_p24_caches_redis.py`. **Pendiente de P2-4:** cachear
catálogos/consultas frecuentes + barrido N+1.

### P2-5 · CSP a nivel Django (R14, #3) — `✅` (PR #106)
**Por qué:** defensa en profundidad si alguna vez se sirve HTML fuera de nginx.

#### Estado — `🟢 HECHO` (PR #106, `feature/p2-4-redis-p2-5-csp`)
`django-csp==4.0` + `CSPMiddleware` (tras WhiteNoise: los estáticos no llevan
header) con política **enforce** en todos los entornos —no report-only: la capa
nginx equivalente ya es enforce y en Railway el backend sirve el admin sin
nginx delante, así que report-only lo dejaría sin protección real—. Base
estricta sin `'unsafe-inline'` global ni nonce: `default-src/script-src/
style-src/img-src/font-src/connect-src/base-uri/form-action 'self'`,
`object-src/frame-ancestors 'none'` (alineada con `X_FRAME_OPTIONS=DENY` y más
estricta que la de nginx, que cubre el SPA). Verificado template a template que
el admin de Django 5.2 no tiene inline ejecutable (solo bloques
`type="application/json"`). Las vistas de docs drf-yasg (solo DEBUG, SEC-05)
llevan su relajación mínima **por vista** (`csp_update`: `style-src
'unsafe-inline'` —estilos inyectados por JS—, `img-src data:` —iconos del CSS
de swagger-ui—, `worker-src blob:` —worker de búsqueda de redoc—). Tests:
`tests/api/test_p25_csp.py`.

### P2-6 · Tracing distribuido — OpenTelemetry (R12) — `❌`
**Por qué:** hay Celery + Kafka + agentes; sin trace correlacionado es difícil diagnosticar.

**Tareas:** instrumentar Django + Celery + Kafka con OTel; exportar a Sentry/colector.
**DoD:** un request se sigue de extremo a extremo (web→tarea→evento).
**Esfuerzo:** ~2 días. **Owner:** devops. **→ CTF si se difiere.**

---

## FASE P3 — Evolutivo (según producto)

### P3-1 · 2FA/MFA para admin/superusuario Omni (R5) — `❌`
TOTP para cuentas privilegiadas. ~2 días. **Owner:** equipo-backend. **→ CTF.**

### P3-2 · RAG para agentes (#6) — `❌`
pgvector + embeddings; retrieval de historial de cliente (cobranza) y gastos similares
(clasificador). Construir sobre el gateway P2-1. ~5–8 días. **Owner:** equipo-agentes. **→ CTF.**

### P3-3 · WebSockets full-duplex (#5b) — `❌`
Solo si el producto necesita full-duplex; hoy SSE cubre servidor→cliente. Django Channels +
Daphne. ~3 días. **Owner:** equipo-backend. **→ CTF (evaluar necesidad real antes).**

---

## Secuenciación recomendada

```
Semana 1 ─┬─ P0-1 RLS (lo más largo, arrancar ya)
          ├─ P0-2 pip/npm audit  ┐ baratos, en paralelo
          └─ P0-3 secret scan    ┘
Semana 2 ─┬─ P1 (throttling, idempotencia, axes, JWT, auditoría inmutable, IDOR, backups)
          └─ P2-1 Gateway LLM (arrancar en paralelo)
Semana 3 ─┬─ P2-2..P2-6 (agentes async, costos LLM, CACHES, CSP Django, OTel)
Futuro  ──┴─ P3 (2FA, RAG, WebSockets) ── cada uno con su CTF
```

## CTFs a abrir si algo se difiere

Cualquier item P2/P3 que no entre en su ventana se difiere con un CTF en
[`../ctf/`](../ctf/) (`vence_en` + owner), según R-PROC-6. Candidatos directos:
P2-1 (gateway LLM), P2-6 (OTel), P3-1 (2FA), P3-2 (RAG), P3-3 (WebSockets).

## Definition of Done del plan

Cada tarea pasa el gate completo de [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md):
build verde, tests verdes, `/security-review`, `/code-review`, revisión de gaps, cero deuda
nueva (o CTF), auto-checklist R-CODE/R-PROC. PRs pequeños y focales (R-PROC-2), en draft,
por la rama correcta según [`FLUJO_DE_TRABAJO.md`](../FLUJO_DE_TRABAJO.md) (fix/hotfix desde
`main` para lo P0; feature desde `develop` para el resto).
