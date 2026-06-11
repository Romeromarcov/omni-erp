# Planes de ejecución — roadmap de producto

Este directorio contiene los planes de ejecución vivos del proyecto, derivados del
[`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) (fuente de verdad de planificación).
Cada plan es accionable: fases, tareas concretas con rutas de archivos reales, estimación
de esfuerzo, dependencias y **Definition of Done** alineado al gate de cierre
([`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md)).

> Estos planes NO sustituyen al Plan Maestro: lo aterrizan en frentes de trabajo paralelos.
> Cuando un plan se ejecuta, su deuda diferida se rastrea con un CTF en [`../ctf/`](../ctf/).

## Índice

| Plan | Archivo | Objetivo | Esfuerzo | Estado |
|------|---------|----------|----------|--------|
| **0** | [`00-piloto-distribuidora.md`](00-piloto-distribuidora.md) | Arrancar la distribuidora en producción (online): `.exe` + primeros usuarios + seguimiento por API | ~3–4 días | **EN CURSO** (0.1 y 0.4-tooling ✅; restan 0.2, seed real, 0.5, 0.6) — ⛔ tras el P0 de auditoría (Plan Maestro §5.2) |
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
