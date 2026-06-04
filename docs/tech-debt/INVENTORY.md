# Inventario de deuda técnica

> Registro de deuda técnica **conocida** de baja/media prioridad, sin fecha de vencimiento
> formal. La deuda **crítica/alta con fecha y dueño** se rastrea como Compromiso Técnico
> Fechado en [`docs/ctf/`](../ctf/) (R-PROC-6). Este inventario es la referencia histórica
> y de baja prioridad; al promover un ítem a crítico, se le crea su CTF.
>
> Última actualización: 2026-06-03 (auditoría plan cero-dudas).

## TODOs activos en código

| # | Ubicación | Descripción | Severidad |
|---|---|---|---|
| TD-1 | `frontend/src/pages/Finanzas/Cajas/CajaMovimientosListPage.tsx:69` | Botón "Exportar" sin handler (`TODO: exportar informe`) | Baja |
| TD-2 | `frontend/src/pages/Finanzas/CuentasBancarias/CuentaBancariaMovimientosListPage.tsx:65` | Botón "Exportar" sin handler (`TODO: exportar informe`) | Baja |
| TD-3 | `frontend/src/pages/Ventas/FacturasFiscales/FacturaFiscalDetailPage.tsx:280` | Usa `'temp-id'` como `idCliente` en vez del ID real del cliente | Media |

> Backend: **0 TODO/FIXME/XXX reales** en `apps/` (verificado 2026-06-03).

## Bugs reales detectados en auditoría (vía ruff E9/F8)

| # | Ubicación | Bug | Estado |
|---|---|---|---|
| BUG-1 | `apps/ventas/views.py` (`crear_transaccion_financiera_pago`) | `Decimal` re-importado localmente (antes en línea 465) lo volvía variable local de toda la función → `UnboundLocalError` en pagos en **divisa** (`moneda_pago != moneda_base`); la función re-lanzaba, así que el pago en divisa **fallaba**. No detectado por falta de test de esa ruta. | ✅ **Corregido** (2026-06-03) — guard ruff F823 bloqueante en CI. *Pendiente:* test conductual de pago en divisa (TEST-5). |
| BUG-DUP-1 | `apps/finanzas/serializers.py`, `apps/finanzas/views.py` | **Definiciones duplicadas** (corroboradas por mypy `no-redef`): `CajaFisicaSerializer` **3×**, `DatafonoSerializer` **2×**, el ViewSet `PlantillaMaestroCajasVirtualesViewSet` **2×**, + 13 imports redundantes. Python liga al punto de definición, así que registros/usos podían apuntar a definiciones distintas según su posición. | ✅ **Corregido** (2026-06-03). Eliminadas las definiciones muertas (sombreadas) conservando las activas; verificado que todos los `import`/`serializer_class` ligaban a la última (comportamiento preservado). 17 F811 a **cero**; **F811 ahora bloqueante en CI** (impide reintroducir duplicados). Tests de finanzas verdes. |

> Nota mypy (2026-06-03): las 27 alertas de mypy son en su mayoría limitaciones de
> inferencia (p.ej. `buckets[bucket]["total"] += saldo` en `cuentas_por_cobrar/services.py:147`
> es **correcto** en runtime; mypy ensancha el dict heterogéneo a `object`). Las únicas
> accionables son las `no-redef` de BUG-DUP-1. mypy sigue no-bloqueante hasta anotar tipos.

## Deuda arquitectónica conocida (ver Plan Maestro §4.3)

- **Acoplamiento a Venezuela en el núcleo** — lógica VE dispersa (`apps/fiscal`, IGTF en
  `apps/ventas`, libros SENIAT); migración gradual (strangler fig) a `apps/localizacion`/
  `apps/localizacion_ve` (§3.7). En curso.
- **`saas` middleware fail-open** — revisar a fail-closed al activar `SAAS_VERIFICAR_SUSCRIPCION`.
- **Dos `PROJECT_LOG.md` divergentes** (raíz vs `backend/`) — `backend/PROJECT_LOG.md` es el
  vigente; archivar el de la raíz.
- **Service Workers / offline real** (portales) — pendiente.
- **Prometheus/Grafana** — pendiente (Sentry ya está).

## Deuda de tooling (detectada en auditoría cero-dudas)

- **`semgrep` no instala en Windows nativo** — requiere WSL/Docker. Los tests/tooling locales
  corren dentro del contenedor Docker (Linux). Documentado para futuros colaboradores.
- **OpenAPI: el proyecto usa `drf-yasg`, no `drf-spectacular`** — el plan cero-dudas menciona
  `drf-spectacular`; al cablear el job `contract`/`schemathesis` decidir si se migra o se usa
  `drf-yasg` como fuente del esquema.
- Varios checks de CI en `continue-on-error` (ruff/mypy/diff-cover/audits) — endurecer por
  GATE-1 (ver [`docs/audit/ESTADO_PLAN_CERO_DUDAS.md`](../audit/ESTADO_PLAN_CERO_DUDAS.md)).

## Hallazgos BAJA/MEDIA abiertos de auditorías

Ver el detalle por severidad + CWE + archivo:línea en
[`docs/AUDITORIA_2026-06-02.md`](../AUDITORIA_2026-06-02.md) (15 BAJA + 12 MEDIA registrados).
Los residuales con seguimiento activo (SEC-1, COOP/CORP, CSP) están en
[`docs/audit/ESTADO_PLAN_CERO_DUDAS.md`](../audit/ESTADO_PLAN_CERO_DUDAS.md).
