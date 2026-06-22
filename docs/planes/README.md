# Planes de ejecución — roadmap de producto

Este directorio contiene los planes de ejecución vivos del proyecto, derivados del
[`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) (fuente de verdad de planificación).
Cada plan es accionable: fases, tareas concretas con rutas de archivos reales, estimación
de esfuerzo, dependencias y **Definition of Done** alineado al gate de cierre
([`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md)).

> Estos planes NO sustituyen al Plan Maestro: lo aterrizan en frentes de trabajo paralelos.
> Cuando un plan se ejecuta, su deuda diferida se rastrea con un CTF en [`../ctf/`](../ctf/).

## Roadmap por features (ejecución autónoma) — verificado 2026-06-21

> Unidad = **feature** (no sprint ni fecha). Solo es DONE lo que un test/comando confirma en verde.
> Un agente ejecuta cada feature PENDING sin bloqueantes por su cuenta (ver Plan Maestro §5.1-bis:
> rama → PR a `develop` → QA_AGENT + SEC_AGENT → automerge con CI verde). Los ítems **OWNER** requieren
> acción humana no técnica (secrets, RLS en prod, branch protection, firma, billing) y **no** son autónomos.

| Feature | Estado | Criterio de done (comando/test) | Bloqueado por |
|---|---|---|---|
| Enforcement de cierre de período fiscal | ✅ DONE (2026-06-21) | `validar_periodo_abierto`; factura/devolución en período `CERRADO` → 400; `tests/api/test_periodo_fiscal_enforcement.py` (7) verde | — |
| `AbonoCxPViewSet` write-guard (paridad con CxC) | PENDING | PUT/PATCH/DELETE → 405 y `create` delega en `registrar_abono_cxp` atómico; test | ninguno |
| Re-vincular CxP ↔ `FacturaCompra` | PENDING | `registrar_factura_compra` setea `id_factura_compra` en la CxP; test | ninguno |
| FK de usuario real en `AsientoContable` | PENDING | `id_usuario_registro` = FK a `core.Usuario`; migración reversible; test | ninguno |
| Offline POS — cerrar ciclo frontend (CTF-008) | PENDING | `PosPage` encola `VentaOffline` y hace flush al reconectar (`client_uuid→id_nota_venta`); test FE | ninguno (backend `#171` REAL_DONE) |
| `localizacion_ve` — 4 adapters faltantes | PENDING | `GeneradorDocumentoLegalVE`/`LibroLegalVE`/`ProveedorTasasVE`/`MetodosPagoLocalesVE` registrados; test de registry | ninguno (framework REAL_DONE) |
| Services de costeo real + MRP básico (1.I) | PENDING | service de costeo por OF + MRP; test de integración | ninguno (modelos OF/etapas REAL_DONE) |
| UI módulos API-only (compras, CxP, contabilidad, tesorería, RRHH/nómina) | PENDING | páginas en sidebar con TanStack Query + rhf/zod; tests de servicio FE | ninguno |
| Ratchet cobertura frontend 55%→80% | PENDING | escalón de cobertura vitest sube; CI verde | ninguno |
| RLS en producción (CTF-012) | OWNER/BLOCKED | rol BD no-dueño + `RLS_ENABLED=True` en prod; suite RLS verde | rol BD + secret (owner) |
| Backups con restore probado (P0-9) | OWNER | backup nocturno real en S3 + restore documentado | secret `BACKUP_DB_HOST` (owner) |
| Billing SaaS (Plan C4) · Push Odoo (D3, CTF-011) · Firma de apps (CTF-010) | OWNER/BLOCKED | ver plan respectivo | credenciales/decisión owner |

## Índice de planes (detalle)

| Plan | Archivo | Objetivo | Esfuerzo | Estado |
|------|---------|----------|----------|--------|
| **0** | [`00-piloto-distribuidora.md`](00-piloto-distribuidora.md) | Arrancar la distribuidora en producción (online): `.exe` + primeros usuarios + seguimiento por API | — | **EN CURSO — siguiente hito (1.F).** P0 de auditoría CERRADO; software listo. Restan: carga de datos reales + operación 30 días (acción de owner/datos, no código) |
| **A** | [`01-offline-first.md`](01-offline-first.md) | Offline-first real (ADR-001) por niveles | ~6–8 semanas | DIFERIDO ([CTF-008](../ctf/CTF-008.md)) |
| **B** | [`02-apps-multiplataforma.md`](02-apps-multiplataforma.md) | Apps firmadas + CI de empaquetado (Windows → Android → desktop; iOS futuro) | ~3–4 semanas | PLANIFICADO ([CTF-010](../ctf/CTF-010.md)) |
| **C** | [`03-panel-saas.md`](03-panel-saas.md) | Consola del proveedor SaaS (planes, tenants, suscripciones, signup) | ~2.5 semanas (+ billing futuro) | **COMPLETADO (MVP)** — C1–C3 ✅ 2026-06-07; falta toggle en staging; C4 (billing) diferido |
| **D** | [`04-cobranza-standalone-lubrikca-odoo.md`](04-cobranza-standalone-lubrikca-odoo.md) | Standalone de Cobranza en Lubrikca integrado a Odoo por el Hub | ~2–3 semanas | **COMPLETADO (MVP)** — D1/D4 ✅, D2 falta validación ops con credenciales reales; D3 diferido ([CTF-011](../ctf/CTF-011.md)) |
| **05** | [`05-seguridad-hardening.md`](05-seguridad-hardening.md) | Hardening de seguridad y resiliencia (RLS, CI de CVEs, gateway LLM, idempotencia, 2FA…) | ~3–4 semanas | **EN CURSO** — P0-1 RLS infra ✅ (activación bloqueada por [CTF-012](../ctf/CTF-012.md)); P1–P3 pendientes |

## Secuenciación recomendada

```
Ahora ─┬─ Plan 0 (distribuidora online)        ← operación, días
       ├─ Plan D (Lubrikca / Odoo cobranza)     ← aprobado, en paralelo, 2–3 sem
       └─ Plan C1+C2 (panel SaaS para pilotos)   ← en paralelo, ~2.5 sem
Luego ─┬─ Plan B (Windows firmado + CI, Android)
       └─ Plan A (offline-first, 6–8 sem)        ← el más largo; arrancar pronto aunque diferido
Futuro ── iOS · Billing/medición LLM · offline Nivel 3
```

## Deuda asociada (CTF)

- [CTF-008](../ctf/CTF-008.md) — Offline-first real (Plan A).
- [CTF-009](../ctf/CTF-009.md) — Drift `es_superusuario_innova` (frontend) vs `es_superusuario_omni` (backend).
- [CTF-010](../ctf/CTF-010.md) — Firma de código + CI de empaquetado de apps (Plan B).
