# Checklist de corrección R-CODE (A3) — verificado 2026-06-03

> **DoD A3.** Checklist de los invariantes R-CODE críticos, por invariante, con evidencia
> y el **guard automatizado / test** que lo bloquea en CI. Priorizadas las apps de dinero/
> contables. Complementa [`SECURITY_REVIEW_2026-06-02.md`](SECURITY_REVIEW_2026-06-02.md) (A2).

## Invariantes verificados

| Invariante | Estado | Evidencia | Guard / test que lo bloquea |
|---|---|---|---|
| **R-CODE-1** multi-tenant (`get_queryset` por empresa) | 🟢 | ~99 ViewSets tenant filtran por empresa | **TEST-1** auto-descubierto (`test_aislamiento_cobertura.py`) — falla si se añade un ViewSet sin aislamiento; + tests de aislamiento por módulo |
| **R-CODE-2** PostgreSQL, nunca SQLite | 🟢 | `settings_base.py:122` falla si no es PostgreSQL ("SQLite no está soportado") | CI corre contra `postgres:17`; fail-closed en settings |
| **R-CODE-4** Decimal para dinero | 🟢 | **0 `FloatField`** en `ventas/compras/finanzas/contabilidad/fiscal/cxc/cuentas_por_cobrar/tesoreria/nomina` | property-based **TEST-3** (IVA/IGTF: redondeo a 2 decimales, sumas exactas) |
| **R-CODE-6** soft delete (no hard delete) | 🟢 | `ActiveFilterMixin` + `deleted_at`/`activo`; sin `.delete()` físico en flujos de negocio | tests de módulo |
| **R-CODE-11** asiento contable atómico | 🟢 | `generar_asiento_o_fallar` centralizado, usado en `contabilidad`, `compras`, `cxc/acuerdos`, `inventario` dentro de `@transaction.atomic`; `ventas`/`tesoreria` vía `generar_asiento` | `emitir_factura_fiscal` es `@transaction.atomic` (verificado); 4 tests de R-CODE-11 (auditoría previa) |
| **Concurrencia** `select_for_update` | 🟢 | en `inventario` (stock), `cuentas_por_cobrar`/`cuentas_por_pagar` (saldos), `cxc/fraccionamiento`, `fiscal` (correlativos), `ventas` | **TEST-4** race de reserva de stock (no overselling) + `test_fiscal_concurrencia` (correlativos) |
| **R-PROC-5** migraciones reversibles | 🟡 | mayoría reversibles; `finanzas/migrations/0022` usa `RunPython.noop` (documentado) | `makemigrations --check` bloqueante (sin drift) |
| Sin inyección SQL (`.raw/.extra`) | 🟢 | 0 ocurrencias | **semgrep `omni-no-raw-sql` BLOQUEANTE** |
| Sin `eval/exec/shell=True`/`verify=False` | 🟢 | 0 ocurrencias | **semgrep reglas Omni BLOQUEANTES** |
| Sin `UnboundLocalError`/uso-antes-de-asignar | 🟢 | BUG-1 corregido | **ruff F823 BLOQUEANTE** |
| Sin definiciones duplicadas | 🟢 | BUG-DUP-1 corregido | **ruff F811 BLOQUEANTE** |

## Residuales (rastreados)

- **R-PROC-5 / `finanzas/migrations/0022_create_sample_devices`**: reversa `RunPython.noop`
  (datos de muestra, no destructivo). Bajo riesgo; reescribir reversa o sacar de migraciones
  → **inventario de deuda** (`docs/tech-debt/INVENTORY.md`).
- Defensa en profundidad `fields="__all__"` → **CTF-005**.

## Conclusión A3

Los invariantes R-CODE críticos están **verificados y, en su mayoría, bloqueados
automáticamente en CI** (semgrep propio, ruff F823/F811, TEST-1 aislamiento, makemigrations
--check). Lo residual está aceptado y rastreado (CTF / inventario). **A3 cerrado.**
