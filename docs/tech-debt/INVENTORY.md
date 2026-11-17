# Inventario de deuda técnica

> Registro de deuda técnica **conocida** de baja/media prioridad, sin fecha de vencimiento
> formal. La deuda **crítica/alta con fecha y dueño** se rastrea como Compromiso Técnico
> Fechado en [`docs/ctf/`](../ctf/) (R-PROC-6). Este inventario es la referencia operativa
> de deuda estática y de baja prioridad; al promover un ítem a crítico, se le crea su CTF.
>
> Última medición verificada: **2026-11-17** sobre `origin/develop @ ff2bdb6`
> (Plan 06 — Tarea 3.5).

## Métricas estáticas medidas en código actual (`origin/develop @ ff2bdb6`)

Medición ejecutada con `git grep -I -n` sobre el repositorio actual (separando código ejecutable, tests, docstrings y documentación):

| Indicador | Alcance medido | Conteo real | Desglose / observación | Seguimiento |
|---|---|---:|---|---|
| `# noqa` | `backend/apps/` + `backend/config/` (`.py`) | **201** *(51 archivos)* | `195` en `apps/` + `6` en `config/` (`0` en tests dentro de `apps/`). Adicional: `79` en `backend/tests/` + `backend/tests_eval/`. | Plan 06 — Tarea 3.4 |
| `TODO` / `FIXME` / `HACK` / `XXX` | `backend/apps/` + `backend/config/` + `frontend/src/` (`.py`/`.ts`/`.tsx`, `\b...\b`) | **0** reales | Las 12 coincidencias literales son 9 usos de la palabra española `"TODO"` en comentarios/docstrings y 3 fixtures `'XXX'` en tests FE. En `infra/nginx/nginx.prod.conf:26` queda **1** `# TODO: set specific server_name in prod (M-SEC-6)`. | Limpio en código de app |
| `eslint-disable` | `frontend/src/` (`.ts`/`.tsx`) | **40** | **38** en código de producción (`react-hooks/exhaustive-deps`, `security/detect-object-injection`, `react-refresh/only-export-components`, `security/detect-unsafe-regex`) + **2** en `frontend/src/__tests__/api.test.ts` (documentadas como FP). | Plan 06 — Tarea 3.4 |
| `print(` | `backend/apps/` + `backend/config/` (`.py`) | **5** | **1** en código ejecutable (`backend/config/celery.py:34`, `debug_task`) + **4** en docstrings de ejemplo (`agentes/cobranza.py:18`, `agentes/reorden.py:22`, `localizacion_ve/calendario.py:9-10`). **0** en lógica de negocio de `apps/`. | R-CODE-3 / Plan 06 |
| `console.log` | `frontend/src/` (`.ts`/`.tsx`) | **0** | **0** en código `.ts`/`.tsx` (`1` solo en ejemplo Markdown de `frontend/src/services/README_PagosService.md:166`). | Limpio (R-CODE-3) |
| `any` explícito (`: any`, `as any`, `<any>`, `any[]`) | `frontend/src/` (`.ts`/`.tsx`) | **0** | **0** en código `.ts`/`.tsx` (`2` solo en ejemplo Markdown de `frontend/src/services/README_PagosService.md:156,178`). | Limpio (R-CODE-3) |
| `Response({...str(e\|exc\|err)...})` | `backend/apps/` + `backend/config/` (`:!*test*`) | **38** *(15 archivos)* | `activaciones/views.py` (3), `bots_ingest/views.py` (4), `compras/views.py` (4), `finanzas/views.py` (7), `finanzas/views_libro_caja.py` (2), `finanzas/views_pagos_terceros.py` (2), `fiscal/views_libros.py` (1), `fiscal/views_parafiscales.py` (1), `gastos/views.py` (2), `gestion_aprobaciones/views.py` (1), `gestion_documental/views.py` (1), `inventario/views.py` (2), `nomina/views.py` (2), `sync/views.py` (1), `tesoreria/views.py` (5). | Plan 06 — H5 / Tarea 1.1 |

### Comandos reproducibles

```bash
git grep -I -n '# noqa' -- backend/apps backend/config
git grep -I -n -E '\b(TODO|FIXME|HACK|XXX)\b' -- backend/apps backend/config frontend/src infra
git grep -I -n 'eslint-disable' -- frontend/src
git grep -I -n -E '\bprint\s*\(' -- backend/apps backend/config
git grep -I -n -E 'console\.log|:\s*any\b|as\s+any\b' -- frontend/src
git grep -I -n -E 'Response\(\{[^}]*str\((e|exc|err)\)' -- backend/apps backend/config ':!*test*'
```

## Ítems históricos TD-1..TD-3 (ya resueltos)

| # | Ubicación original | Descripción original | Estado verificado (2026-11-17) |
|---|---|---|---|
| TD-1 | `frontend/src/pages/Finanzas/Cajas/CajaMovimientosListPage.tsx:64-84` | Botón "Exportar" sin handler | ✅ **Resuelto** — `exportCSV()` con `downloadCsv(...)` y montos en string crudo (R-CODE-4). |
| TD-2 | `frontend/src/pages/Finanzas/CuentasBancarias/CuentaBancariaMovimientosListPage.tsx:60-80` | Botón "Exportar" sin handler | ✅ **Resuelto** — `exportCSV()` con `downloadCsv(...)` y montos en string crudo (R-CODE-4). |
| TD-3 | `frontend/src/pages/Ventas/FacturasFiscales/FacturaFiscalDetailPage.tsx` | Uso de `'temp-id'` como `idCliente` | ✅ **Resuelto** — `'temp-id'` eliminado del código fuente frontend. |

## Bugs reales detectados y cerrados en auditorías previas

| # | Ubicación | Bug | Estado |
|---|---|---|---|
| BUG-1 | `apps/ventas/views.py` (`crear_transaccion_financiera_pago`) | `Decimal` re-importado localmente producía `UnboundLocalError` en pagos en divisa. | ✅ **Corregido** (2026-06-03) — guard `ruff F823` bloqueante en CI. |
| BUG-DUP-1 | `apps/finanzas/serializers.py`, `apps/finanzas/views.py` | Definiciones duplicadas sombreadas (17 `F811`). | ✅ **Corregido** (2026-06-03) — guard `ruff F811` bloqueante en CI. |
| Backfill Fase 3 | `tests/` (antiguos `BUG` en `test_*`) | ~30 bugs de producto (P0, `OperacionCambioDivisa`, `transferir-entre-cajas`, `AbonoCxPViewSet`, etc.). | ✅ **Cerrados en gran mayoría** vía workstream P0 (PRs #64–#73), CTF-013/015 y Track B (PRs #182–#186); residuales de Hub documentados en [`docs/integracion-hub/ESTADO.md`](../integracion-hub/ESTADO.md) §4.1. |

## Deuda arquitectónica y operativa vigente (ver Plan Maestro §4.3 y Plan 06)

- **RLS real en entornos (`CTF-012` / Plan 06 Fase 2):** las políticas `FORCE ROW LEVEL SECURITY` cubren el esquema en BD, pero el runtime conecta aún con el rol dueño y `bypass='on'` por defecto hasta crear el rol no-dueño `omni_app` y migrar variables en Railway.
- **Acoplamiento a Venezuela en el núcleo:** lógica VE dispersa (`apps/fiscal`, IGTF en `apps/ventas`, libros SENIAT); migración gradual (strangler fig) a `apps/localizacion` / `apps/localizacion_ve` (2/6 adapters implementados; faltan 4).
- **`saas` middleware fail-open:** revisar a fail-closed al activar `SAAS_VERIFICAR_SUSCRIPCION=True`.
- **Deuda residual de seguridad (Plan 05):** `P1-5` (auditoría inmutable en BD), `P1-6` (barrido IDOR por objeto), `P1-7` (cargar secrets de backup del owner), `P2-2` (agentes síncronos en vistas → Celery), `P2-3` (persistencia dedicada de costos LLM), `P2-4` (cacheo de consultas calientes + N+1), `P2-6` (OpenTelemetry).
- **Consolidación de `banca_electronica`:** `apps/banca_electronica/models.py` mantiene un scaffold de `CuentaBancariaEmpresa` separado de `finanzas.CuentaBancariaEmpresa` (usado por `tesoreria` y `finanzas`). Se aborda en [`docs/planes/08-conciliacion-pagos-y-paridad-odoo.md`](../planes/08-conciliacion-pagos-y-paridad-odoo.md).
- **Offline POS frontend (`CTF-008`):** backend atómico `#171` y `salesOutbox`/`useOutboxFlush` existen, falta cerrar el ciclo en `PosPage`.
- **Tooling, dependencias y CI (Plan 06):** migración a `ruff` (D2), segunda pasada Decimal en formularios/helpers FE (Tarea 4.2); `semgrep` requiere WSL/Docker en Windows nativo. *(Pines de las 4 dependencias, Dependabot semanal, desacople de auditoría CVE a `nightly.yml` y Actions Node 24 cerrados en PR `#289` — Plan 06 Tareas `1.3` y `3.6`.)*
- **Advisory upstream sin parche no-disruptivo en `frontend/package-lock.json` (`picomatch <= 4.0.7` / `GHSA-fc5q-39xc-vjpf`):** **15 vulnerabilidades `HIGH`** transitivas en el toolchain de desarrollo/build (`vite`, `vitest`, `tinyglobby`, `@rollup/pluginutils`, `fdir`, `vite-plugin-pwa`, `@typescript-eslint/typescript-estree`, etc.; `picomatch` instalado en `4.0.4`, donde `npm audit fix --force` degradaría `vite` a `6.2.7` con *breaking change*). No afecta el runtime de producción del navegador y queda mitigado por el desacople a `nightly.yml` (reporte automático con issue) y bloqueo exclusivo en la rama de release `main` introducido en PR `#289`.

## Hallazgos históricos de auditorías

- **Auditoría integral 2026-06-10:** hallazgos CRÍTICO/ALTO cerrados en workstream P0 (PRs #64–#73); documento archivado en [`docs/auditorias/archivo/AUDITORIA_INTEGRAL_2026-06-10.md`](../auditorias/archivo/AUDITORIA_INTEGRAL_2026-06-10.md).
- **Auditoría integral 2026-06-21:** hallazgos cerrados en Track B (PRs #182–#186); reporte en [`docs/AUDITORIA_2026-06-21.md`](../AUDITORIA_2026-06-21.md) y snapshots en [`docs/_archive/2026-06-21/`](../_archive/2026-06-21/).
- **Histórico 2026-06-02:** [`docs/_archive/AUDITORIA_2026-06-02.md`](../_archive/AUDITORIA_2026-06-02.md) (archivada).
