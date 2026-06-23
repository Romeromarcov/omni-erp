# Orchestrator Log — Omni ERP

Registro append-only de los ítems cerrados por el loop autónomo.

- 2026-06-18 ✅ CTF-005 — whitelist explícita de campos en serializers (ventas/compras/core); elimina `fields="__all__"` (CWE-915, defensa en profundidad) + test guard. Rama `claude/funny-albattani-cqsuck`.
[2026-06-18T13:01:23Z] ✅ CTF-005 whitelist serializers PR#140 merged
[2026-06-18T13:11:02Z] ✅ CTF-005 fase 2 (finanzas+nomina whitelist) commit 7872c7c
[2026-06-18T13:30:08Z] ✅ CTF-005 fase 2 (finanzas+nomina) PR#141 merged
[2026-06-18T13:36:34Z] ✅ CTF-005 fase 3 (contabilidad/tesoreria/fiscal/cxc/cxp/gastos/costos whitelist)
[2026-06-18T13:56:26Z] ✅ CTF-005 fase 3 PR#142 merged
[2026-06-18T18:23:40Z] ✅ CTF-005 fase 4 (cierre total, 68 serializers, 18 apps) commit 5f852a0
[2026-06-18T18:46:59Z] ✅ CTF-005 fase 4 (cierre total) + fix CVE undici PR#143 merged — 0 __all__ en todo el proyecto
[2026-06-18T19:03:30Z] ✅ CTF-008 Nivel 1 réplica local IndexedDB (persistencia caché) commit 661a317
[2026-06-18T19:23:05Z] ✅ CTF-008 Nivel 1 réplica local IndexedDB PR#144 merged
[2026-06-18T19:48:48Z] ✅ 1.I costeo real persistido (CostoProduccion) commit c412772
[2026-06-18T20:14:03Z] ✅ CTF-008 Nivel 2 backend pull de deltas (apps/sync) commit 9a4561f
[2026-06-18T20:38:06Z] ✅ CTF-008 Nivel 2 pull de deltas (apps/sync) PR#147 merged
[2026-06-18T20:51:17Z] ✅ CTF-008 N2 replay idempotente ventas POS (test+doc) commit 3676654
[2026-06-18T21:09:45Z] ✅ CTF-008 N2 replay idempotente ventas POS PR#149 merged
[2026-06-18T21:16:16Z] ✅ CTF-008 N2 sync pull variantes_producto commit b806686
[2026-06-18T21:36:15Z] ✅ CTF-008 N2 sync pull variantes_producto PR#150 merged
[2026-06-18T21:40:30Z] ✅ CTF-008 N2 cliente del pull (syncService) commit 7d936f2
[2026-06-18T22:06:00Z] ✅ FE-CRIT-1 ProveedorIntegracionFormPage → react-hook-form+zod commit 5510ec3
[2026-06-18T22:25:53Z] ✅ FE-CRIT-1 ProveedorIntegracionFormPage rhf+zod PR#152 merged
[2026-06-18T22:29:37Z] PlanFormPage rhf+zod commit b2f7660 (FE-CRIT-1)
[2026-06-18T22:50:53Z] FE-CRIT-1 PlanFormPage rhf+zod PR#153 merged — 16/16 FormPage en react-hook-form
[2026-06-18T23:17:42Z] Q1 cobertura transaccionFinancieraService PR#154 merged
[2026-06-18T23:39:15Z] ✅ Q1 cobertura cuentaBancariaService PR#155 merged
[2026-06-19T00:04:44Z] ✅ CTF-008 N2 outbox ventas POS (salesOutbox) PR#156 merged
[2026-06-19T01:13:42Z] ✅ ADR-012 modelo transaccional venta POS offline commit 09f8d1a
[2026-06-19T02:18:04Z] ✅ ADR-012 modelo transaccional POS offline PR#157 merged (desbloqueado vía update-branch)
[2026-06-19T02:20:22Z] ✅ contrato/builder sobre venta offline (ADR-012) commit d6033ce
[2026-06-19T02:40:34Z] ✅ contrato/builder sobre venta offline (ADR-012) PR#160 merged
[2026-06-19T02:43:00Z] ✅ hook useOutboxFlush reenvío al reconectar (ADR-012) commit 2444f5f
[2026-06-19T03:01:56Z] ✅ hook useOutboxFlush (ADR-012) PR#161 merged
[2026-06-19T03:04:00Z] ✅ cobertura pagosService (Q1) commit 1ea26fc
[2026-06-19T03:41:03Z] ✅ cobertura pagosService (Q1) PR#162 merged
[2026-06-19T03:42:21Z] ✅ cobertura devolucionesPos (Q1) commit 9be8d01
[2026-06-19T11:09:29Z] ✅ cobertura devolucionesPos (Q1) PR#163 merged
[2026-06-19T12:53:10Z] ✅ decimal.js total documento en 4 formularios venta (FE-HIGH-7) PR#167 merged
[2026-06-19T13:10:59Z] ✅ decimal.js totales solo-lectura ventas+libros fiscales (FE-HIGH-7) PR#168 merged
[2026-06-19T13:30:34Z] ✅ decimal.js sumas cantidades inventario (FE-HIGH-7) PR#169 merged — barrido FE-HIGH-7 completo
[2026-06-19T15:58:08Z] ✅ endpoint atómico venta POS offline (ADR-012) PR#171 merged

## Loop autónomo 2026-06-22 — Auditoría 2026-06-21 (Track B) + Integration Hub (Track A) + cierre docs (Track C)

[2026-06-22T04:12:26Z] ✅ Track B-1 período fiscal en COMPRAS (recepción+factura, guard validar_periodo_abierto, 6 tests) PR#182 merged
[2026-06-22T03:45:04Z] ✅ Track B-2 CxP bloquea CRUD libre (http_method_names, espejo CxC P0, 6 tests) PR#183 merged
[2026-06-22T04:12:26Z] ✅ Track B-3a re-vincula CxP→FacturaCompra (FK id_recepcion + migración 0007, 2 tests) PR#184 merged
[2026-06-22T04:41:44Z] ✅ Track B-3b FK real id_usuario_registro en AsientoContable + flujo compras (migración 0012, 3 tests) PR#185 merged
[2026-06-22T05:09:23Z] ✅ Track B-3c FX multimoneda en registrar_efectos_pago (convierte monto_base a moneda empresa, 3 tests) PR#186 merged — TRACK B (auditoría 2026-06-21) COMPLETO
[2026-06-22T05:39:17Z] ✅ Track A-1 IH persiste facturas_venta → FacturaFiscal + líneas desde Odoo (8 tests) PR#187 merged
[2026-06-22T06:17:50Z] ✅ Track A-2 IH persiste pagos (cobros cliente reconciliados→finanzas.Pago, history-only, 6 tests) PR#188 merged — IH Fase 2 inbound COMPLETO
[2026-06-22T06:52:06Z] ✅ Track A-3a IH registry dinámico de conectores (ConectorProveedor.clase_conector + import_string, migración 0006, 6 tests) PR#189 merged
[2026-06-22T07:30:00Z] ✅ Track A-3b IH conector genérico REST (GenericRestConnector config-driven, R-CODE-8, 18 tests) PR#190 merged — TRACK A (Integration Hub) COMPLETO
[2026-06-22T08:35:07Z] ✅ Cola-2nd FX comisión datafono → moneda base empresa (convertir_monto, 1 test multimoneda) PR#192 merged
[2026-06-22T08:58:34Z] ✅ Cola-2nd asiento usuario en inventario AJUSTE_INVENTARIO PR#193 merged
[2026-06-22T09:21:20Z] ✅ Cola-2nd asiento usuario en cxc PAGO_CXC (abono directo + acuerdo) PR#194 merged
[2026-06-22T09:45:32Z] ✅ Cola-2nd asiento usuario en finanzas PAGO_TERCERO (abono+reintegro) PR#195 merged
[2026-06-22T10:07:57Z] ✅ Cola-2nd asiento usuario en fiscal PAGO_PARAFISCAL PR#196 merged
[2026-06-22T10:31:16Z] ✅ Cola-2nd asiento usuario en nomina NOMINA PR#197 merged
[2026-06-22T10:53:12Z] ✅ Cola-2nd asiento usuario en tesoreria CAMBIO_DIVISA PR#198 merged
[2026-06-22T11:18:46Z] ✅ Cola-2nd asiento usuario en VENTAS (nota/factura/devolución, 5 sites) PR#199 merged — barrido asiento-usuario COMPLETO (7 flujos)
[2026-06-22T11:42:50Z] ✅ Cola-2nd TasaCambioError→400 en PagoViewSet (pago divisa sin tasa) PR#200 merged — items 1-3 cola secundaria COMPLETOS
[2026-06-22T11:44:26Z] 📋 Cola-2nd item 4 IH followups DOCUMENTADO Y DEFERIDO en ESTADO.md §4.1 (reconciliación parcial/multi-factura y pagos proveedor→CxP requieren enriquecer conector Odoo + decisión de producto; facturas_compra aún no persistido). PR docs-only.
[2026-06-22T11:44:26Z] 🎉 SESIÓN COMPLETA — Track A (Integration Hub Fase 2 inbound 7 entidades + Fase 3 registry dinámico + conector genérico REST), Track B (auditoría 2026-06-21: 5 hallazgos cerrados), Track C (docs reconciliados), cola secundaria (FX comisión + asiento-usuario 7 flujos + TasaCambioError→400). Deferido con diseño documentado: IH conciliación parcial/multi-factura, pagos proveedor→CxP, reembolso POS divisa-sin-tasa. PRs #182-201.

## Módulo Inventario — extensión apps español (goal 2026-06-22)

Decisión owner 2026-06-22: **extender** `inventario`/`almacenes`/`contabilidad`
(no crear app `inventory` paralela en inglés). Roadmap PRs focales → develop:
PR-1 valuación · PR-2 pasos config · PR-3 recepciones · PR-4 entregas ·
PR-5 reportes · PR-6 frontend · PR-7 E2E T01–T12.

[2026-06-22] ✅ PR-1 motor valoración FIFO/Promedio (ValoracionInventario + valuation.py;
asiento por valor_total exacto). Gate local: 38 tests inventario/contab verdes,
sweep 89 callers de registrar_movimiento sin regresión, ruff limpio. PR# pendiente.

[2026-06-22] ✅ PR-1 motor valoración FIFO/Promedio PR#204 merged (CI verde; fixes: Matriz A1 + RLS valoracion).
[2026-06-23] ✅ PR-2 asiento COGS al despachar venta (COSTO_VENTA: DR Costo de Ventas / CR Inventario,
  valuado a valor_total) en el chokepoint registrar_movimiento. Gate local: 3 tests COGS + 94 tests
  de flujos de entrega/asiento sin regresión. PR# pendiente.
[2026-06-23] ✅ PR-3 PasoOperacion: pasos configurables de operación (recepción/entrega) por almacén
  — modelo + CRUD API (/api/inventario/pasos-operacion/) + RLS + matriz A1. Gate local: 5 tests
  (CRUD, orden por secuencia, aislamiento tenant, unicidad). PR# pendiente.
[2026-06-23] ✅ PR-4 stepper de operaciones (OperacionInventario + pasos snapshot + líneas):
  recepción/entrega confirmando pasos uno a uno; el último paso mueve stock (valoración+COGS)
  y posa asientos (RECEPCION_MERCANCIA; venta vía chokepoint confirmar_nota_venta). Revisión
  adversarial SEC/correctness → corregidos 2 BLOCKERS (doble despacho/doble asiento de venta) +
  3 should-fix (monto recepción desde valoración; lock TOCTOU en confirmar_paso; numero anti-carrera).
  Gate local: 5 tests (T03/T04/T05/T12 + tenant) + 24 inventario sin regresión. PR# pendiente.
[2026-06-23] ✅ PR-4 stepper de operaciones PR#207 merged (CI verde; fixes: FK read-only SEC-M1 + diff-cov).
[2026-06-23] ✅ PR-5 reportes de inventario: /api/inventario/reportes/{existencias,movimientos,valoracion}.
  Valoración método-agnóstica (Σ entrada − Σ salida) → correcta para FIFO y Promedio. Gate local:
  5 tests (T08/T09/T10 FIFO+Promedio/T11). PR# pendiente.
[2026-06-23] ✅ PR-5 reportes de inventario PR#208 merged (CI verde).
[2026-06-23] ✅ PR-6 frontend stepper: páginas Recepciones/Entregas (stepper visual, confirma uno a
  uno, bloquea fuera de orden) + reporte Valoración + capa de servicio (operaciones/reportes) + rutas.
  Gate local: tsc -b limpio (mis archivos), eslint limpio, 719 tests vitest verdes, cobertura global
  85.4/74.3/78.8/87.0 sobre umbrales (incl. ratchets services/lib). PR# pendiente.
