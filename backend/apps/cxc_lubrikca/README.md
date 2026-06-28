# apps/cxc_lubrikca — Subproyecto CxC Lubrikca

Motor **determinístico** de cobros, descuentos y conciliación para **Lubrikca**,
construido **dentro de Omni** como app **aislada** y gated por el perfil
`cobranza`. Reutiliza la infraestructura de Omni (auth, tasas BCV/Binance,
Integration Hub→Odoo, abonos/ledger, frontend) **sin alterar la lógica del core**.

- **Fuente de verdad operativa:** Odoo (solo lectura desde Omni; push diferido, CTF-011).
- **Decisión arquitectónica:** [`docs/decisions/ADR-013-cxc-lubrikca-app-dedicada.md`](../../../docs/decisions/ADR-013-cxc-lubrikca-app-dedicada.md).
- **Plan de trabajo:** [`docs/cxc-lubrikca/PLAN_TRABAJO.md`](../../../docs/cxc-lubrikca/PLAN_TRABAJO.md).
- **Mapa de datos / gaps del conector Odoo:** [`docs/cxc-lubrikca/MAPA_DATOS_GAPS.md`](../../../docs/cxc-lubrikca/MAPA_DATOS_GAPS.md).

## Aislamiento (regla dura)

Esta app **solo lee** de las apps del core (`cuentas_por_cobrar`, `finanzas`,
`integration_hub`); **no modifica** su lógica. Si necesita algo del core se hace
por **extensión explícita**, nunca editando el core. Endpoint base:
`/api/cxc-lubrikca/`. Multi-tenant: una empresa (Lubrikca), siempre respetando
`get_queryset()` por empresa.

## Estructura (se puebla por fase)

```
apps/cxc_lubrikca/
├── apps.py                 # AppConfig
├── admin.py
├── models/                 # Fase 1: config con effective dating; Fase 2/3: espejo + bandeja
├── services/               # Fase 2: services/motor/ (lógica pura portada de CxC_Lubrikca)
├── api/router.py           # /api/cxc-lubrikca/  (health + ViewSets por fase)
└── migrations/
```

## Estado por fase

| Fase | Entregable | Estado |
|---|---|---|
| 0 | ADR + scaffold app aislada + mapa de datos/gaps + CI verde | ✅ |
| 1 | Config del motor desde UI (effective dating) | ⏳ |
| 2 | Motor determinístico portado + tests (paridad CxC_Lubrikca) | ⏳ |
| 3 | Captura + bandeja de aprobación (cierre híbrido) | ⏳ |
| 4 | Conciliación (semáforo motor-vs-factura) | ⏳ |
| 5 | Conector Odoo: traer todo lo que el motor necesita (solo lectura) | ⏳ |
| 6 | Frontend (perfil cobranza) | ⏳ |
| 7 | Preparación a producción (config real + validación Odoo) | ⏳ |
