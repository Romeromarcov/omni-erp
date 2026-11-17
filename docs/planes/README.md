# Planes de ejecución — roadmap de producto

Este directorio contiene los planes de ejecución vivos del proyecto, derivados del
[`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) (fuente de verdad de planificación).
Cada plan es accionable: fases, tareas concretas con rutas de archivos reales, estimación
de esfuerzo, dependencias y **Definition of Done** alineado al gate de cierre
([`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md)).

> Estos planes NO sustituyen al Plan Maestro: lo aterrizan en frentes de trabajo paralelos.
> Cuando un plan se ejecuta, su deuda diferida se rastrea con un CTF en [`../ctf/`](../ctf/).

## Roadmap por features (ejecución autónoma) — verificado 2026-11-17 (`develop @ ff2bdb6`)

> Unidad = **feature** (no sprint ni fecha). Solo es DONE lo que un test/comando confirma en verde.
> Un agente ejecuta cada feature PENDING sin bloqueantes por su cuenta (ver Plan Maestro §5.1-bis:
> rama → PR `draft` a `develop` → Gate DoD → revisor independiente `QA + Seguridad` `APROBADO` → `ready` → CI 100 % verde → merge a `develop`). Los ítems **OWNER** requieren
> acción humana no técnica (secrets, RLS en prod, branch protection, firma, billing) y **no** son autónomos.

| Feature | Estado | Criterio de done (comando/test) | Bloqueado por |
|---|---|---|---|
| Enforcement de cierre de período fiscal | ✅ DONE (2026-06-21) | `validar_periodo_abierto`; factura/devolución en período `CERRADO` → 400; `tests/api/test_periodo_fiscal_enforcement.py` (7) verde + compras `#182` | — |
| `AbonoCxPViewSet` write-guard (paridad con CxC) | ✅ DONE (PR `#183`) | PUT/PATCH/DELETE → 405 y `create` delega en `registrar_abono_cxp` atómico; 6 tests | — |
| Re-vincular CxP ↔ `FacturaCompra` | ✅ DONE (PR `#184`) | `CuentaPorPagar.id_recepcion` + `registrar_factura_compra` enlaza `id_factura_compra`; tests | — |
| FK de usuario real en `AsientoContable` | ✅ DONE (PR `#185` + `#193–#199`) | `id_usuario_registro` FK a `core.Usuarios`; migración `0012` y 7 flujos cableados | — |
| Services de costeo real + MRP básico (1.I) | ✅ DONE (`c412772` + `#235` + `#244`) | `costeo_real_orden`, `calcular_mrp`, `CostoProduccion` + UI crear OF/consumir/BOM/rutas + E2E `produccion-completa.flow` | — |
| UI módulos API-only (15 apps + 9 sub-módulos) | ✅ DONE (PRs `#215–#247`) | Páginas en sidebar con TanStack Query + rhf/zod + `toList()` + E2E Playwright cross-módulo | — |
| Ratchet cobertura frontend >80 % | ✅ DONE (`vite.config.ts`) | Thresholds globales `statements: 83`, `lines: 85`, `services >= 91 %`; Vitest verde en CI | — |
| Offline POS — cerrar ciclo frontend (CTF-008) | PENDING | `PosPage` encola `VentaOffline` en `salesOutbox` y hace flush al reconectar (`client_uuid→id_nota_venta`); test FE | ninguno (backend `#171` y hooks `#156/#160/#161` listos) |
| `localizacion_ve` — 4 adapters faltantes + flags | PENDING | `GeneradorDocumentoLegalVE`/`LibroLegalVE`/`ProveedorTasasVE`/`MetodosPagoLocalesVE` registrados; test de registry y empresa no-VE | ninguno (framework REAL_DONE) |
| Limpieza y estabilización (Plan 06 Fases 1–4) | EN CURSO | `str(e)` (1.1), pines/Dependabot (1.3), `ruff` (3.3), barrido `# noqa`/`eslint-disable` (3.4), Decimal FE (4.2) | 2.2/2.3/4.3 requieren owner |
| Omni Connect S2–S12 (Plan 07) | PENDING (S1 ✅ `#261`) | Perfil público NFC, captura lead, `crm.Actividad` + Kanban, dedup `core.Contacto`, conversión `Cliente`, outbox + Odoo `crm.lead`, agentes | ninguno (S2–S6) / credenciales Odoo (S9) |
| Conciliación N:M `AsignacionPago` + Paridad ERP Odoo (Plan 08) | PENDING | `finanzas.AsignacionPago` N:M + saldo a favor `core.Contacto`; diarios/reversión/cierre/reportes contables; procurement RFQ→OC; reabastecimiento/lotes | ninguno (Bloque A + B core) / Odoo real (`CTF-011`) |
| RLS en producción (CTF-012 / Plan 06 Fase 2) | OWNER/BLOCKED | rol BD `omni_app` no-dueño + `bypass='off'` + `RLS_ENABLED=True` en staging→prod; suite RLS verde | rol BD + secret (owner) |
| Backups con restore probado (P0-9 / P1-7) | OWNER/BLOCKED | `backup.yml` + `restore-test.yml` (`#96`) listos; falta bucket + secrets en GitHub Actions | secrets `BACKUP_*` (owner) |
| Billing SaaS (Plan C4) · Push Odoo (D3, CTF-011) · Firma de apps (CTF-010) | OWNER/BLOCKED | ver plan respectivo | credenciales/decisión owner |

## Índice de planes (detalle)

| Plan | Archivo | Objetivo | Esfuerzo | Estado |
|------|---------|----------|----------|--------|
| **0** | [`00-piloto-distribuidora.md`](00-piloto-distribuidora.md) | Arrancar la distribuidora en producción (online): `.exe` + primeros usuarios + seguimiento por API | — | **EN CURSO — siguiente hito (1.F).** Software listo; restan carga de datos reales + operación 30 días (acción de owner/datos) |
| **A** | [`01-offline-first.md`](01-offline-first.md) | Offline-first real (ADR-001) por niveles | ~6–8 semanas | EN PROGRESO parcial (backend `#171` + hooks listos; falta ciclo FE POS — [CTF-008](../ctf/CTF-008.md)) |
| **B** | [`02-apps-multiplataforma.md`](02-apps-multiplataforma.md) | Apps firmadas + CI de empaquetado (Windows → Android → desktop; iOS futuro) | ~3–4 semanas | PLANIFICADO ([CTF-010](../ctf/CTF-010.md)) |
| **C** | [`03-panel-saas.md`](03-panel-saas.md) | Consola del proveedor SaaS (planes, tenants, suscripciones, signup) | ~2.5 semanas (+ billing futuro) | **COMPLETADO (MVP)** — C1–C3 ✅; falta toggle en staging; C4 (billing) diferido |
| **D** | [`04-cobranza-standalone-lubrikca-odoo.md`](04-cobranza-standalone-lubrikca-odoo.md) | Standalone de Cobranza en Lubrikca integrado a Odoo por el Hub (+ app `cxc_lubrikca`) | ~2–3 semanas | **COMPLETADO (MVP + `cxc_lubrikca` Fases 0–6 ✅ `#256`/`#258`, staging desplegado)**; falta go-live prod y D3 ([CTF-011](../ctf/CTF-011.md)) |
| **05** | [`05-seguridad-hardening.md`](05-seguridad-hardening.md) | Hardening de seguridad y resiliencia (RLS, CI de CVEs, gateway LLM, idempotencia, 2FA…) | ~3–4 semanas | **EN CURSO** — P0-1 infra ✅ (activación [CTF-012](../ctf/CTF-012.md)); P1-1..P1-4, P2-1, P2-5 ✅; P1-7/P2-3/P2-4 parciales; P1-5/P1-6/P2-2/P2-6/P3 abiertos |
| **06** | [`06-limpieza-y-estabilizacion.md`](06-limpieza-y-estabilizacion.md) | Limpieza y estabilización: runner, monedas, `uuid7` monótono, RLS real, higiene del repo | ~3–4 semanas (PRs pequeños) | **EN CURSO** — Fase 0 ✅, 1.2/3.2/3.5/4.1 ✅; Fases 1–4 restantes en curso |
| **07** | [`07-omni-connect.md`](07-omni-connect.md) | Omni Connect (tarjetas NFC + perfil público + CRM ligero + outbox Odoo + agentes) — ADR-014 | ~4–6 semanas (S2–S12) | **EN CURSO** — S1 esquema ✅ (`#261`); S2–S12 planificadas en detalle |
| **08** | [`08-conciliacion-pagos-y-paridad-odoo.md`](08-conciliacion-pagos-y-paridad-odoo.md) | Conciliación N:M `AsignacionPago` sobre `core.Contacto` + Paridad ERP estilo Odoo (contabilidad, compras/aprobaciones, inventario/almacenes, banca/Hub) | ~5–7 semanas (PRs focales) | **PLANIFICADO** — listo para ejecución autónoma por fases |

## Secuenciación recomendada

```
Ahora ─┬─ Plan 0 (distribuidora online 1.F)     ← operación/datos, días
       ├─ Plan D / CxC Lubrikca go-live         ← validación Odoo real + promote develop→main
       ├─ Plan 06 (estabilización + RLS real)   ← endurece base de producción
       ├─ Plan 08 Bloque A (AsignacionPago N:M) ← desbloquea pagos multi-factura y Hub Odoo
       └─ Plan 07 (Omni Connect S2–S6)          ← captura NFC + CRM ligero + conversión Cliente
Luego ─┬─ Plan 08 Bloque B (paridad Odoo ERP)   ← contabilidad, compras/aprobaciones, inventario, banca/Hub
       ├─ Offline POS FE (CTF-008) + l10n_ve    ← 4 adapters + flags por capa
       └─ Plan B (Windows firmado + CI, Android)
Futuro ── iOS · Billing/medición LLM · offline Nivel 3 · Plan 05 P3 (2FA/RAG/WS)
```

## Deuda asociada (CTF)

- [CTF-008](../ctf/CTF-008.md) — Offline-first real (Plan A).
- [CTF-010](../ctf/CTF-010.md) — Firma de código + CI de empaquetado de apps (Plan B).
- [CTF-011](../ctf/CTF-011.md) — Push de cobranza a Odoo (outbound, Plan D D3 / Plan 08).
- [CTF-012](../ctf/CTF-012.md) — Rol de BD dedicado no-dueño (activación de RLS, Plan 05 / Plan 06).
