# ADR-013: Subproyecto CxC Lubrikca como app dedicada y aislada dentro de Omni

**Estado:** Aceptado
**Fecha:** 2026-06-27
**Autor(es):** Marco Romero, Claude Opus 4.8

## Contexto

Lubrikca necesita un sistema **determinístico** de cobros, descuentos y
conciliación con reglas de negocio muy específicas (disparador neto-objetivo,
apilamiento aditivo de descuentos, reselección de lista por método/ruta, contado
por ventana de días hábiles, BCV-completo topado al diferencial real,
equivalentes congelados por abono, regla de mezcla→Binance, promo de primera
compra, devoluciones opción D, cierre híbrido y semáforo de conciliación).

Existen tres fuentes de trabajo previo:

- **CxC_Lubrikca** (`C:\Users\PC\Proyectos\CxC_Lubrikca`, ~94% tests): el motor
  determinístico puro + conciliación + auditoría de hora. Lógica portable.
- **GestionCxC** (FastAPI + Odoo): configuración del motor **desde UI** + flujo de
  aprobación por roles + límites por producto.
- **Omni** (este repo): auth JWT/roles, tasas BCV+Binance (`finanzas.TasaCambio` +
  conector `tasas_ve`), Integration Hub (Odoo XML-RPC inbound), abonos/ledger
  (`cuentas_por_cobrar`), frontend React/MUI con perfil `cobranza` (Plan D).

La pregunta de diseño: **¿dónde vive este motor?** ¿Se mezcla en `cxc`
("Cobranza Inteligente") o en `cuentas_por_cobrar` (ledger)? ¿O en una app nueva?

## Decisión

**Se construye una app nueva y aislada: `apps/cxc_lubrikca`.**

1. **App dedicada.** Todo el dominio Lubrikca (motor, config con effective
   dating, bandeja de aprobación, conciliación) vive en `apps/cxc_lubrikca`. No
   se mezcla con `cxc` (proceso de cobranza asistido por IA, ADR-009) ni con
   `cuentas_por_cobrar` (ledger contable).
2. **Aislamiento estricto.** La app **solo lee** de las apps del core
   (`cuentas_por_cobrar`, `finanzas`, `integration_hub`) y **no modifica** su
   lógica. Si necesita algo del core, se hace por **extensión explícita** (p. ej.
   un modelo propio que referencia un `AbonoCxC` por FK para estampar
   equivalentes congelados), **nunca** editando el core.
3. **Feature-flag por perfil `cobranza`.** El backend monta el router siempre en
   `/api/cxc-lubrikca/`; el gating efectivo de la UI lo hace el frontend con
   `appProfile.ts` (`VITE_APP_PROFILE=cobranza`, `isModuleEnabled`). No se añade
   gating condicional en `INSTALLED_APPS` (Omni no lo usa para otras apps; ver
   recon Fase 0) para no romper migraciones ni el resto del sistema.
4. **Odoo solo lectura.** Odoo es la fuente de verdad operativa. El Integration
   Hub lee Odoo (inbound). **Omni nunca escribe a Odoo** (push outbound D3
   diferido, [CTF-011]). Google Sheets se descarta (la data vive en Odoo y se
   replica a Omni).
5. **Sin MVP iterativo.** Se construye todo, se prueba, se configura en
   producción y se valida contra el Odoo real de Lubrikca, y recién entonces se
   arranca la operación.

## Alternativas consideradas

- **Mezclar en `cxc`.** Rechazada: `cxc` es cobranza asistida por IA (agentes,
  MCP, acuerdos); acoplar el motor determinístico a ese módulo volátil viola la
  separación de la ADR-009 y mezcla ciclos de cambio distintos.
- **Mezclar en `cuentas_por_cobrar`.** Rechazada: es el ledger contable estable y
  crítico; meterle reglas de negocio específicas de un cliente lo contamina.
- **Repo standalone separado (mantener CxC_Lubrikca como servicio aparte).**
  Rechazada: duplicaría auth, tasas, conector Odoo y frontend que Omni ya tiene
  (Plan D). El objetivo es reutilizar la infraestructura de Omni.

## Consecuencias

- **Regla de dependencia:** `cxc_lubrikca` → puede leer `cuentas_por_cobrar`,
  `finanzas`, `integration_hub`, `core`. Esas apps **NO** dependen de
  `cxc_lubrikca`.
- **Portabilidad:** la lógica pura de CxC_Lubrikca se porta a
  `services/motor/` sin acoplar a Odoo/Sheets (dataclasses → modelos
  Omni/Odoo-synced); sus ~37 tests de lógica pura se portan a pytest de Omni.
- **Equivalentes congelados:** se añaden por extensión (modelo propio que
  referencia el abono), no editando `AbonoCxC` del core.
- **Gaps del conector Odoo:** el motor necesita campos que el conector inbound
  aún no trae (marca/categoría de línea, `delivery_status`, `qty_delivered`,
  devoluciones por `return_id`, `amount_total_signed_usd`). Se documentan en
  [`MAPA_DATOS_GAPS.md`](../cxc-lubrikca/MAPA_DATOS_GAPS.md) y se cierran en Fase 5
  por **extensión** del conector (solo lectura).
- **Multi-tenant:** Lubrikca = una empresa; se respeta `get_queryset()` por
  empresa en todos los ViewSets (R-CODE-1).
- **Endpoint:** `/api/cxc-lubrikca/`. Health: `/api/cxc-lubrikca/health/`.

## Trazabilidad

| Pieza | Origen | Acción |
|---|---|---|
| Motor descuentos, conciliación, equivalentes, auditoría de hora | CxC_Lubrikca | Portar lógica + tests |
| Mapeo de campos Odoo 18 | CxC_Lubrikca (`docs/ODOO_MAPEO.md`) | Reusar en conector |
| Config UI (límites, condiciones, promos, tasas) + aprobación por roles | GestionCxC | Rescatar/portar patrón |
| Auth, tasas, Integration Hub, abonos/ledger, frontend, perfil cobranza | Omni | Reusar tal cual |
