# Planes de ejecución — roadmap de producto

Este directorio contiene los planes de ejecución vivos del proyecto, derivados del
[`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) (fuente de verdad de planificación).
Cada plan es accionable: fases, tareas concretas con rutas de archivos reales, estimación
de esfuerzo, dependencias y **Definition of Done** alineado al gate de cierre
([`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md)).

> Estos planes NO sustituyen al Plan Maestro: lo aterrizan en frentes de trabajo paralelos.
> Cuando un plan se ejecuta, su deuda diferida se rastrea con un CTF en [`../ctf/`](../ctf/).

## Roadmap por features (ejecución autónoma) — verificado 2026-11-24 (`develop`, cierre Ola 6 `#333–#337` + Plan 09 `#318`, `#338–#349`)

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
| Offline POS — ciclo frontend + push optimista (`CTF-008`) | 🔶 EN PROGRESO (técnico ✅ `#335`; campo pendiente) | `PosPage` + `salesOutbox` + `useOutboxFlush` + `POST /api/sync/push/` optimista (`#335`) ✅; resta únicamente condición operativa #4 (pruebas reales 8–24h sin red) | ninguno |
| `localizacion_ve` — 6/6 adapters + strangler fig | ✅ DONE (`#312` + `#334`) | `localizacion_ve` 6/6 puertos (`#312`) + strangler fig cableado en `fiscal`, `ventas` y `nomina` (`#334`) con E2E VE vs NoOp | — |
| Limpieza y estabilización (Plan 06 Fases 1–4) | ✅ AUTOMATIZABLE CERRADO (`#288–#302`, `#333`) | Fases automatizables + limpieza mypy/ruff/TZ cerrada en `#333`; restan ítems OWNER (`CTF-012` / backups / Railway) | `2.2`/`2.3`/`4.3` requieren owner |
| Omni Connect S1–S12 (Plan 07) | ✅ DONE (`S1–S12` 100 %, `#261`, `#313–#317`, `#337`) | Perfil público NFC/QR, captura lead, `crm.Actividad` + Kanban, dedup `core.Contacto`, conversión `Cliente`, outbox + Odoo `crm.lead` + smoke test live QA1 (`#337`) | — |
| Conciliación N:M `AsignacionPago` + Paridad ERP Odoo (Plan 08) | ✅ DONE (`100 %` Bloques A + B + `CTF-011`) | `finanzas.AsignacionPago` N:M + saldo a favor `core.Contacto`; diarios/reversión/cierre/reportes contables; procurement RFQ→OC; reabastecimiento/lotes; cierre `CTF-011` | — |
| Ola 6 — Consolidación técnica y hardening (`#333–#337`) | ✅ DONE (`#333–#337` en `develop`) | PR-31 (`#333`) roadmap+mypy/ruff/TZ; PR-32 (`#334`) strangler-fig; PR-33 (`#335`) `POST /api/sync/push/` optimista; PR-34 (`#336`) `SAAS_FAIL_CLOSED` + 2FA TOTP; PR-35 (`#337`) smoke live QA1 Connect→Odoo | — |
| Plan 09 — ERP Clase Mundial VE (Trimonetario + Dual + TMS + Portales + IA + Migrador) | ✅ AUTOMATIZABLE COMPLETADO (`#318`, `#338–#349`) | Motor Trimonetario (`#318`) ✅; Dualidad (`#338`/`#339`) ✅; Motor Comercial (`#340`) ✅; Access Studio (`#341`) ✅; SENIAT 360° (`#342`) ✅; Nómina Dual VE (`#343`) ✅; Supply Chain (`#344`) ✅; TMS IA/ePOD (`#345`) ✅; Portales BE/FE (`#346`/`#347`) ✅; Chatter/WhatsApp + 5 Agentes IA (`#348`) ✅; Migrador 1-Click Odoo `READ-ONLY`/CSV (`#349`) ✅ | Restan únicamente ítems `OWNER` (`CTF-012`, `P1-7`, `CTF-010`, `CTF-008 #4`) |
| RLS en producción (CTF-012 / Plan 06 Fase 2) | OWNER/BLOCKED | rol BD `omni_app` no-dueño + `bypass='off'` + `RLS_ENABLED=True` en staging→prod; suite RLS verde | rol BD + secret (owner) |
| Backups con restore probado (P0-9 / P1-7) | OWNER/BLOCKED | `backup.yml` + `restore-test.yml` (`#96`) listos; falta bucket + secrets en GitHub Actions | secrets `BACKUP_*` (owner) |
| Billing SaaS (Plan C4) · Push Odoo (D3, CTF-011) · Firma de apps (CTF-010) | OWNER/BLOCKED | ver plan respectivo | credenciales/decisión owner |

## Índice de planes (detalle)

| Plan | Archivo | Objetivo | Esfuerzo | Estado |
|------|---------|----------|----------|--------|
| **0** | [`00-piloto-distribuidora.md`](00-piloto-distribuidora.md) | Arrancar la distribuidora en producción (online): `.exe` + primeros usuarios + seguimiento por API | — | **EN CURSO — siguiente hito (1.F).** Software listo; restan carga de datos reales + operación 30 días (acción de owner/datos) |
| **A** | [`01-offline-first.md`](01-offline-first.md) | Offline-first real (ADR-001) por niveles | ~6–8 semanas | **EN PROGRESO** (POS offline FE ✅; resta push optimista de ediciones en Ola 6 PR-33 y pruebas campo 8–24h — [CTF-008](../ctf/CTF-008.md)) |
| **B** | [`02-apps-multiplataforma.md`](02-apps-multiplataforma.md) | Apps firmadas + CI de empaquetado (Windows → Android → desktop; iOS futuro) | ~3–4 semanas | **AVANZADO** — AppImage/updater implementados; pendiente firma de apps en CI ([CTF-010](../ctf/CTF-010.md)) |
| **C** | [`03-panel-saas.md`](03-panel-saas.md) | Consola del proveedor SaaS (planes, tenants, suscripciones, signup) | ~2.5 semanas (+ billing futuro) | **COMPLETADO (MVP)** — C1–C3 ✅; hardening `SAAS_FAIL_CLOSED` en Ola 6 PR-34; C4 (billing) diferido |
| **D** | [`04-cobranza-standalone-lubrikca-odoo.md`](04-cobranza-standalone-lubrikca-odoo.md) | Standalone de Cobranza en Lubrikca integrado a Odoo por el Hub (+ app `cxc_lubrikca`) | ~2–3 semanas | **COMPLETADO (MVP + `cxc_lubrikca` Fases 0–6 ✅ `#256`/`#258`, staging desplegado)**; falta go-live prod y D3 ([CTF-011](../ctf/CTF-011.md) cerrado en Plan 08) |
| **05** | [`05-seguridad-hardening.md`](05-seguridad-hardening.md) | Hardening de seguridad y resiliencia (RLS, CI de CVEs, gateway LLM, idempotencia, 2FA…) | ~3–4 semanas | **EN CURSO** — P0-1 infra ✅ ([CTF-012](../ctf/CTF-012.md)); P1–P2 automatizables ✅; **P3-1 (2FA/TOTP)** en Ola 6 PR-34; restan ítems owner |
| **06** | [`06-limpieza-y-estabilizacion.md`](06-limpieza-y-estabilizacion.md) | Limpieza y estabilización: runner, monedas, `uuid7` monótono, RLS real, higiene del repo | ~3–4 semanas (PRs pequeños) | **AUTOMATIZABLE CERRADO (`#288–#302`)** — deuda residual mypy/ruff/TZ en Ola 6 PR-31; restan ítems exclusivos de owner |
| **07** | [`07-omni-connect.md`](07-omni-connect.md) | Omni Connect (tarjetas NFC + perfil público + CRM ligero + outbox Odoo + agentes) — ADR-014 | ~4–6 semanas (S2–S12) | **COMPLETADO (`100 %` ✅)** — S1 (`#261`) + S2–S12 (`#313–#317`); smoke live QA Connect→Odoo en Ola 6 PR-35 |
| **08** | [`08-conciliacion-pagos-y-paridad-odoo.md`](08-conciliacion-pagos-y-paridad-odoo.md) | Conciliación N:M `AsignacionPago` sobre `core.Contacto` + Paridad ERP estilo Odoo (contabilidad, compras/aprobaciones, inventario/almacenes, banca/Hub) | ~5–7 semanas (PRs focales) | **COMPLETADO (`100 %` ✅)** — Bloques A + B + cierre `CTF-011` mergeados en `develop` |
| **09** | [`09-erp-clase-mundial-ve.md`](09-erp-clase-mundial-ve.md) | ERP Clase Mundial VE: Motor Trimonetario (USD/VES/USDT) + Multi-Tasa, Contabilidad Dual (`FISCAL`/`GERENCIAL`), Blindaje SENIAT + Imprenta Digital, Precios por Brecha, Nómina Dual VE, Logística TMS IA/GPS/Delivery, Supply Chain, RBAC Granular y Portales (Vendedores, Clientes, Conductores) + Chatter/WhatsApp + 5 Agentes IA + Migrador 1-Click | 6 Olas (`#318`, `#338–#349`) | **✅ AUTOMATIZABLE COMPLETADO (`100 %`)** — Olas 1A–6B completas en `develop`; restan únicamente ítems `OWNER` (`CTF-012`, `P1-7`, `CTF-010`, `CTF-008 #4` + `1.F`) |

## Secuenciación recomendada

```
Completado ✅ ─┬─ Ola 6 (`#333–#337`)           ← roadmap+mypy/ruff → l10n strangler-fig → sync push CTF-008 → 2FA/SaaS → smoke Odoo QA
               └─ Plan 09 Olas 1A–6B (`#318–#349`) ← Trimonetario, Dualidad, Precios, RBAC, SENIAT, Nómina VE, Supply Chain, TMS IA, Portales, WhatsApp/IA, Migrador 1-Click
Ahora (OWNER) ─┬─ Plan 0 (distribuidora 1.F)     ← carga de datos reales + operación 30d + campo offline CTF-008 #4
               ├─ Plan D / CxC Lubrikca go-live  ← validación Odoo real + promote develop→main
               └─ Hardening / Firma / Backups    ← rol omni_app (CTF-012), secrets BACKUP_* (P1-7), firma apps (CTF-010)
Futuro ────────── iOS · Billing/medición LLM · offline Nivel 3
```

## Deuda asociada (CTF)

- [CTF-008](../ctf/CTF-008.md) — Offline-first real (Plan A).
- [CTF-010](../ctf/CTF-010.md) — Firma de código + CI de empaquetado de apps (Plan B).
- [CTF-011](../ctf/CTF-011.md) — Push de cobranza a Odoo (outbound, Plan D D3 / Plan 08).
- [CTF-012](../ctf/CTF-012.md) — Rol de BD dedicado no-dueño (activación de RLS, Plan 05 / Plan 06).
