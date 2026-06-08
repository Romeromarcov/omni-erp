# Plan 05 — Hardening de seguridad y resiliencia

> Plan de ejecución derivado de una auditoría de seguridad sobre `main` (2026-06-07).
> Aterriza en frentes accionables los hallazgos de la auditoría más las recomendaciones
> adicionales. Alineado a [`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) §2 (R-CODE /
> R-PROC / R-PROD) y al gate de cierre [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md).

| Campo        | Valor                                  |
|--------------|----------------------------------------|
| **Estado**   | PLANIFICADO                            |
| **Fecha**    | 2026-06-07                             |
| **Esfuerzo** | ~3–4 semanas (repartibles en paralelo) |
| **Owner**    | equipo-backend / equipo-agentes / devops |

---

## 0. Resumen — estado actual por hallazgo

Leyenda: ✅ implementado · ⚠️ parcial · ❌ falta.

### De tu checklist original

| # | Medida | Estado | Evidencia |
|---|--------|--------|-----------|
| 1 | Row Level Security (PostgreSQL) | ❌ | Aislamiento solo a nivel de app (`get_empresas_visible()`, filtros en `get_queryset()`); sin `CREATE POLICY` |
| 2 | CORS | ✅ | `django-cors-headers`; prod fail-closed (`settings_prod.py:48-61`) |
| 3 | Security headers | ✅ | Django prod (`settings_prod.py:64-77`) + nginx con CSP (`infra/nginx/nginx.prod.conf:39-47`) |
| 4 | Arquitectura desacoplada / gateway LLM / agnóstica | ❌ | `anthropic.Anthropic()` directo en 5 sitios, modelos hardcodeados |
| 4b | Fallback a otros modelos si el principal falla | ⚠️ | Hay fallback **a reglas deterministas**, no a otro LLM ni a otro proveedor |
| 5 | Arquitectura orientada a eventos / IA en background | ⚠️ | Celery+Redis+Kafka existen; sugerencias diarias en Beat. Pero agentes en vistas corren **síncronos** (sin `.delay()`) |
| 5b | WebSockets para streaming | ⚠️ | Hay **SSE** en chat (`StreamingHttpResponse`); no hay Django Channels (full-duplex) |
| 6 | RAG | ❌ | Sin pgvector / embeddings / vector store / retrieval |
| 7 | Frontend comprimido sin source maps | ✅ | Vite sin `build.sourcemap`, bundle minificado, gzip nginx |
| 8 | Rate limiting | ✅ | Nginx (`login 5/m`, `api 60/m`) + `django-ratelimit` en login + tests |
| 9 | Cache | ⚠️ | Redis/Celery, WhiteNoise, nginx `expires 1y`, PWA Workbox. **Falta** `CACHES` de Django (cache de ORM) |
| 10 | Escalabilidad | ✅ | uvicorn workers, Celery `concurrency=4`, stateless, Docker |
| 11 | Monitoreo | ✅ | Sentry (`send_default_pii=False`), logging estructurado, healthchecks, `RegistroAuditoria` |
| 12 | Sin API keys/secretos en código | ✅ | `SECRET_KEY` obligatorio desde env; todo desde env; `.env` en `.gitignore` |
| 13 | Validación de inputs / anti-inyección | ✅ | ORM parametrizado, Serializers DRF, `RunSQL` literales; frontend Zod + react-hook-form (35+ forms) |

### Recomendaciones adicionales (no estaban en la checklist)

| # | Recomendación | Estado |
|---|---------------|--------|
| R1 | `pip-audit` + `npm audit` en CI (escaneo de dependencias) | ❌ |
| R2 | Secret scanning (gitleaks/trufflehog) pre-commit + CI | ❌ |
| R3 | Throttling DRF global (más allá del login) | ❌ |
| R4 | Rotación/revocación de JWT (blacklist al logout) | ⚠️ verificar |
| R5 | 2FA/MFA para admin/superusuario Omni | ❌ |
| R6 | Política de contraseñas + bloqueo de cuenta (django-axes) | ❌ |
| R7 | Permisos a nivel objeto auditados (no solo filtro de queryset) | ⚠️ |
| R8 | Backups automáticos + prueba de restore de PostgreSQL | ⚠️ verificar |
| R9 | Idempotencia en endpoints de pago/creación (claves idempotentes) | ❌ |
| R10 | Circuit breaker / timeouts en llamadas LLM | ❌ |
| R11 | Observabilidad de costos LLM (tokens por tenant) | ❌ |
| R12 | Tracing distribuido (OpenTelemetry) — Celery + Kafka + agentes | ❌ |
| R13 | Auditoría inmutable (`RegistroAuditoria` no editable/borrable) | ⚠️ verificar |
| R14 | CSP a nivel Django (`django-csp`, nonce por request) | ❌ (existe en nginx) |

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
verde con el filtro de aplicación deshabilitado; sin regresión en `tests_api/`.
**Esfuerzo:** ~4–6 días. **Owner:** equipo-backend.

### P0-2 · `pip-audit` + `npm audit` en CI (R1) — `❌`
**Por qué:** ya hubo 5 CVEs de Django parcheados a mano (commit `c96c25a`). Hay que detectarlos
solos, no por suerte.

**Tareas:**
1. Job de CI `pip-audit -r backend/requirements.txt` (falla en severidad alta/crítica).
2. Job `npm audit --audit-level=high` en `frontend/`.
3. Documentar excepción temporal vía CTF si una CVE no tiene fix inmediato.

**DoD:** CI rojo ante CVE alta/crítica nueva; ambos jobs corriendo en cada PR.
**Esfuerzo:** ~0.5 día. **Owner:** devops.

### P0-3 · Secret scanning (R2) — `❌`
**Por qué:** complementa "no secretos en código" detectándolos **antes** del push, no después.

**Tareas:**
1. `gitleaks` como hook pre-commit + job de CI sobre el diff.
2. Barrido histórico una vez; rotar cualquier secreto que aparezca.

**DoD:** gitleaks en pre-commit y CI; barrido histórico limpio (o secretos rotados).
**Esfuerzo:** ~0.5 día. **Owner:** devops.

---

## FASE P1 — Alto (semana 1–2)

### P1-1 · Throttling DRF global (R3, #4) — `❌`
**Por qué:** el rate limit fino solo cubre login. El resto de la API (incluida escritura) no
tiene techo de abuso a nivel aplicación.

**Tareas:** `DEFAULT_THROTTLE_CLASSES` + `DEFAULT_THROTTLE_RATES` en `settings_base.py`
(anon/user) y throttle más estricto en endpoints de escritura/pago.
**DoD:** throttling activo con tests; documentado.
**Esfuerzo:** ~1 día. **Owner:** equipo-backend.

### P1-2 · Idempotencia en pagos/creación (R9) — `❌`
**Por qué:** ERP financiero; un doble-submit o reintento de red no puede duplicar un pago o
una factura.

**Tareas:** cabecera `Idempotency-Key` + tabla de claves usadas; aplicar en `apps/ventas`
(pagos, confirmar nota) y `apps/cxc`.
**DoD:** reintento con misma clave devuelve el mismo resultado sin duplicar; tests.
**Esfuerzo:** ~2 días. **Owner:** equipo-backend.

### P1-3 · Bloqueo de cuenta + política de contraseñas (R6) — `❌`
**Por qué:** rate-limit por IP no frena fuerza bruta distribuida ni credential stuffing.

**Tareas:** `django-axes` (bloqueo por usuario+IP tras N fallos) + validadores de contraseña
de Django reforzados.
**DoD:** cuenta se bloquea tras N intentos; tests; mensajes que no filtran si el usuario existe.
**Esfuerzo:** ~1 día. **Owner:** equipo-backend.

### P1-4 · Revocación de JWT al logout (R4) — `⚠️ verificar`
**Por qué:** un token robado debe poder invalidarse; el logout debe revocar de verdad.

**Tareas:** confirmar blacklist de refresh tokens (SimpleJWT) activa; logout que la use;
TTL de access corto.
**DoD:** refresh revocado no renueva; test de logout→reuse falla.
**Esfuerzo:** ~0.5 día. **Owner:** equipo-backend.

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

### P1-7 · Backups + prueba de restore de PostgreSQL (R8) — `⚠️ verificar`
**Por qué:** no asumir que Railway lo cubre; un backup sin restore probado no es un backup.

**Tareas:** verificar/configurar backup automático; runbook de restore en
`docs/skills/diagnostico-railway/`; **prueba real de restore** documentada.
**DoD:** restore probado y fechado; runbook escrito.
**Esfuerzo:** ~1 día. **Owner:** devops.

---

## FASE P2 — Medio (semana 2–3)

### P2-1 · Gateway LLM agnóstico + fallback multi-modelo + timeouts/circuit breaker (#4, #4b, R10) — `❌`
**Por qué:** unifica agnosticidad de proveedor, failover real entre modelos, timeouts y
control de fallos en un solo componente. Hoy `anthropic.Anthropic()` está en 5 sitios con
modelos hardcodeados (`apps/agentes/clasificador.py:154`, `cobranza.py:178`, `reorden.py:195`,
`apps/agentes/api/chat.py:330`, `apps/cxc/agents/cobranza_agent.py:44`).

**Tareas:**
1. `backend/libs/llm_gateway.py`: cliente unificado (proveedor/modelo configurable por env).
2. Fallback en cascada: modelo principal → modelo alterno → (último recurso) reglas deterministas.
3. Timeouts + reintentos con backoff + circuit breaker por proveedor.
4. Migrar los 5 call sites al gateway; quitar modelos hardcodeados.

**DoD:** un solo punto de entrada a LLMs; test que simula caída del principal y verifica
failover; sin SDK de proveedor instanciado fuera del gateway.
**Esfuerzo:** ~3 días. **Owner:** equipo-agentes. **→ CTF si se difiere.**

### P2-2 · Mover agentes de las vistas a Celery (#5) — `⚠️`
**Por qué:** ya existe la infra (Celery+Redis+Beat); las vistas que llaman agentes en
`apps/agentes/views.py` corren síncronas y bloquean el request.

**Tareas:** convertir acciones de análisis a `.delay()` / `apply_async()`; devolver job id;
exponer estado (poll o vía SSE existente).
**DoD:** análisis de agentes fuera del request HTTP; test de encolado.
**Esfuerzo:** ~2 días. **Owner:** equipo-agentes.

### P2-3 · Observabilidad de costos LLM por tenant (R11) — `❌`
**Por qué:** control de gasto y detección de abuso; encaja con el billing futuro del Plan C.

**Tareas:** registrar tokens in/out + costo estimado por llamada y por empresa (en el gateway
P2-1); dashboard/contador en `RegistroAuditoria` o tabla dedicada.
**DoD:** consumo por tenant consultable; test de registro.
**Esfuerzo:** ~1.5 días. **Owner:** equipo-agentes.

### P2-4 · `CACHES` de Django con Redis (#9) — `⚠️`
**Por qué:** Redis ya está para Celery; falta cachear queries ORM caras y sesiones.

**Tareas:** `CACHES` con `django-redis`; cachear catálogos/consultas frecuentes; revisar
N+1 con `select_related`/`prefetch_related` en ViewSets de mayor tráfico.
**DoD:** `CACHES` configurado; invalidación correcta; sin N+1 en endpoints calientes.
**Esfuerzo:** ~1.5 días. **Owner:** equipo-backend.

### P2-5 · CSP a nivel Django (R14, #3) — `❌ (existe en nginx)`
**Por qué:** defensa en profundidad si alguna vez se sirve HTML fuera de nginx, y para
`nonce` por request.

**Tareas:** `django-csp`; política equivalente a la de nginx; alinear ambas capas.
**DoD:** header CSP emitido por Django en prod; sin romper assets.
**Esfuerzo:** ~0.5 día. **Owner:** equipo-backend.

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
