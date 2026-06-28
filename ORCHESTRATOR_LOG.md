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
[2026-06-23] ✅ PR-6 frontend stepper PR#209 merged (CI verde: tsc/eslint/api-drift/vitest/E2E).
[2026-06-23] ✅ PR-7 UI config de pasos por almacén/operación (PasosOperacionPage + pasosOperacionService
  CRUD) — completa T02 vía UI (configurar pasos antes de usar el stepper). Gate local: tsc/eslint limpios,
  723 tests vitest, cobertura sobre umbrales (incl. ratchets). PR# pendiente.

## Loop autónomo 2026-06-24 — Frontend app-por-app (Contactos y terceros)

[2026-06-24] ✅ CRM frontend completo (maestro de Clientes) PR#215 merged — el backend ya
  estaba 100% (Cliente/Contacto/Dirección + CRUD + buscar-por-rif/historial-ventas/credito-disponible)
  pero NO existía pantalla. Agregado: ClientesPage (lista+búsqueda+dialog alta/edición+eliminar+drawer
  de detalle con crédito/historial y CRUD inline de contactos y direcciones), clientesService ampliado
  (preservando firmas usadas por ventas/POS) + contactos/direccionesService, crmRoutes+nav 'Clientes (CRM)',
  crmKeys. Tests: 25 page + 16 service vitest + E2E crm.flow. Gate: functions 78.65% (umbral 77),
  tsc 0, lint limpio. Incidente: sesión concurrente borró archivos del repo principal → recuperados al
  worktree aislado; CI verde es el gate autoritativo (ver memoria reference_worktree_docker_ci_workflow).

[2026-06-24] ✅ proveedores frontend completo (maestro de Proveedores) — espejo de CRM. Backend ya 100%
  (Proveedor/ContactoProveedor/CuentaBancariaProveedor + CRUD + buscar-por-rif) sin pantalla. Agregado:
  ProveedoresPage (lista+búsqueda+dialog+eliminar+drawer con CRUD inline de contactos y cuentas bancarias),
  proveedoresService + contactos/cuentasBancariasService, proveedoresRoutes+nav 'Proveedores', proveedoresKeys.
  comprasService NO tocado. Tests: 17 page + 19 service + E2E proveedores.flow. Gate nativo verde:
  functions 79.43% (umbral 77), stmts 85.75, branches 74.39, lines 87.3, services funcs 95.02; tsc 0, lint limpio.
  PR# pendiente.

[2026-06-24] ✅ proveedores frontend PR#216 merged (CI verde tras 3 intentos; el dragger real de cobertura
  era clientesService branches 37.93%, no proveedores — cubierto a 79%, services branches 88%).
[2026-06-24] ✅ gastos frontend completo (workflow de aprobación) — backend ya 100%. Agregado: GastosPage
  (lista+filtro estado+StatusChip, dialog alta/edición con detalles inline de imputación, Aprobar/Rechazar
  gated por estado, drawer detalle), CategoriasGastoPage, ReembolsosPage (Procesar pago/Anular gated),
  gastosService (4 sub-servicios: categorías/gastos/detalles/reembolsos con todas las acciones),
  gastosRoutes+nav 'Gastos', gastosKeys. Tests: 75 (43 service + 32 página) + E2E gastos.flow. ADEMÁS
  endurecimiento de cobertura services branches 84.93→91.55 (tests puros de contabilidadService [era 0% ramas],
  monedas, metodosPagoEmpresaActiva, clientesService). Gate nativo verde: global funcs 79.51, services 91.55
  branches; 948 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ gastos frontend PR#217 merged (CI verde 1er intento; cobertura endurecida services branches 91.55).
[2026-06-24] ✅ despacho frontend completo (máquina de estados logística). Backend ya 100%. Agregado:
  DespachosPage (lista+filtro estado+StatusChip, crear-desde-nota-venta con selector almacén origen,
  botones de transición Iniciar ruta/Entregar/Devolver/Cancelar gated por puedeTransicionar replicando
  TRANSICIONES del backend, drawer con líneas read-only + enlace PDF), despachoService (acciones +
  detalleDespachoService read-only), despachoRoutes+nav 'Despacho', despachoKeys. Tests: 49 (37 service +
  18 página, puros sin userEvent) + E2E despacho.flow. Gate nativo verde: services branches 91.99,
  global funcs 79.70, despachoService 100%; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ despacho frontend PR#218 merged (CI verde 1er intento).
[2026-06-24] ✅ costos frontend completo (costeo producción). Backend ya 100% (CRUD 3 entidades sin acciones).
  Agregado: CostosPage (tabs/sub-secciones para CostoProduccion/CostoEstandar/AnalisisVariacion con CRUD,
  StatusChip de variación FAVORABLE/DESFAVORABLE/NEUTRO), costosService (3 sub-servicios), costosRoutes+nav
  'Costos', costosKeys. Tests servicio puros + página + E2E costos.flow. Gate nativo verde: services branches
  92.32, global funcs 79.07, 1046 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ costos frontend PR#219 merged (CI verde 1er intento).
[2026-06-24] ✅ control_asistencia frontend completo (horarios, asignaciones, marcaje, resúmenes). Backend ya 100%.
  Agregado: ControlAsistenciaPage (4 tabs: Horarios CRUD+desactivar, Asignaciones CRUD+finalizar+filtro empleado,
  Registros lista/por-empleado-fecha/hoy + Marcar asistencia, Resúmenes generar+aprobar gated por estado_revision
  con StatusChip), controlAsistenciaService (4 sub-servicios con todas las acciones), rutas+nav 'Control de Asistencia',
  controlAsistenciaKeys. Tests: 81 (56 service puros + 25 página) + E2E. Gate nativo verde: services branches 93.36,
  global funcs 79.52, 1127 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ control_asistencia frontend PR#220 merged (CI verde 1er intento).
[2026-06-24] ✅ servicio_cliente frontend completo (mesa de ayuda). Backend ya 100%. Agregado: TicketsPage
  (filtros estado/prioridad, StatusChip, drawer detalle con timeline de interacciones + agregar comentario,
  acciones gated Asignar agente/Cambiar estado/Escalar), CategoriasTicketPage, BaseConocimientoPage (chip
  visibilidad), FeedbackPage (calificación 1-5); servicioClienteService (5 sub-servicios con todas las acciones
  incl. dashboard), rutas+nav 'Servicio al Cliente', servicioClienteKeys. Tests: 107 (67 service puros + 40 página)
  + E2E. Gate nativo verde: services branches 93.95, global funcs 79.64, 1234 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ servicio_cliente frontend PR#221 merged (CI verde 1er intento).
[2026-06-24] ✅ gestion_aprobaciones frontend completo (motor de aprobaciones). Backend ya 100% (CRUD 4 entidades,
  sin @actions). Agregado: ConfiguracionAprobacionesPage (tabs CRUD Tipo+Flujo), SolicitudesAprobacionPage
  (filtro estado+StatusChip, drawer con timeline de RegistroAprobacion + Registrar decisión = POST registro +
  PATCH estado), aprobacionesService (4 sub-servicios + cambiarEstado), rutas+nav 'Aprobaciones', aprobacionesKeys.
  Tests: 63 (33 service puros + 30 página) + E2E. Gate nativo verde: services branches 94.05, global funcs 79.46;
  tsc 0, lint limpio (flaky OperacionesCambio ajeno requiere reintento CI). PR# pendiente.

[2026-06-24] ✅ gestion_aprobaciones frontend PR#222 merged.
[2026-06-24] ✅ gestion_documental frontend completo (gestión documental con archivos). Backend ya 100%.
  Agregado: DocumentosPage (panel de carpetas CRUD+navegación, lista documentos+búsqueda, Subir (multipart
  vía postForm), Descargar (URL pre-firmada del backend + ancla download), Eliminar archivo, drawer con CRUD
  inline de Vínculos y Permisos), gestionDocumentalService (4 sub-servicios + subir/descargar/eliminarArchivo),
  rutas+nav 'Documentos', gestionDocumentalKeys. Tests: 58 (35 service puros + 23 página) + E2E. Gate nativo
  verde: services branches 94.35, global funcs 79.6, 1355 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ gestion_documental frontend PR#225 merged (9 apps frontend completas).
[2026-06-24] ✅ fix E2E PR#226 merged — develop a E2E verde. Causa raíz: (1) bug real fetchUsuarios devolvía
  {results} paginado → SolicitudesAprobacionPage crasheaba (usuarios.map), fix central toList en users.ts;
  (2) CostosPage no auto-seleccionaba/validaba id_moneda (→400); (3) spec costos asumía producto sembrado
  (seed no siembra productos) → ahora siembra vía API. Lección: correr E2E specs localmente + toList en todo fetch de lista.
[2026-06-24] ✅ notificaciones frontend (centro de notificaciones). API estrecha (mis-notificaciones + marcar-leida).
  Agregado: NotificacionesPage (inbox: lista, toggle no leídas, marcar leída/todas, StatusChip, estado vacío),
  notificacionesService (misNotificaciones/marcarLeida con toList), rutas+nav 'Notificaciones', notificacionesKeys.
  Integra con NotificationBell existente (sin duplicar). vite.config: preview.proxy /api para E2E local. Tests: 12
  (7 service + 5 página). Gate verde: services branches 94.37, global funcs 79.66, 1367 tests; tsc 0, lint limpio.
  E2E no verificable localmente (rehidratación de sesión no dispara en preview build, afecta también crm.flow) → CI lo valida. PR# pendiente.

[2026-06-24] ✅ notificaciones frontend PR#227 merged (10 apps; E2E verde en CI).
[2026-06-24] ✅ banca_electronica frontend completo (CRUD cuentas bancarias de empresa). Backend ya 100%.
  Agregado: CuentasBancariasEmpresaPage (DataTable + dialog alta/edición + eliminar; tipo corriente/ahorro,
  moneda, saldo, activa con StatusChip), bancaElectronicaService (CRUD con toList), rutas+nav 'Banca Electrónica',
  bancaElectronicaKeys. Tests: 19 (9 service puros + 10 página). Gate verde: services branches 94.41, global
  funcs 79.83, 1385 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ banca_electronica frontend PR#228 merged (11 apps).
[2026-06-24] ✅ migracion_datos frontend completo (plantillas/procesos/errores de migración). Backend ya 100%.
  Agregado: MigracionDatosPage (Tabs: Plantillas CRUD con manejo de 403 superuser-write, Procesos lista+alta
  con StatusChip estado, Errores solo-lectura filtrable por proceso), migracionDatosService (3 sub-servicios
  con toList, service 100% cobertura), rutas+nav 'Migración de Datos', migracionDatosKeys. Tests: 45 (30 service
  puros + 15 página). Gate verde: services branches 94.55, global funcs 80.02, 1427 tests; tsc 0, lint limpio.
  (Flagged tech-debt: OperacionesCambio.test.tsx flaky timeout 5s → task_dd4597a5.) PR# pendiente.

[2026-06-24] ✅ migracion_datos frontend PR#229 merged (12 apps).
[2026-06-24] ✅ agentes frontend completo (Agentes IA / predicciones). Backend ya 100% (predicciones + acciones).
  Agregado: AgentesPage (lista predicciones con filtros agente/resultado + StatusChip, Responder/Evaluar por fila,
  panel de análisis cobranza/reorden/personalización + clasificar-gasto, métricas del clasificador), agentesService
  (todas las acciones con toList), rutas+nav 'Agentes IA', agentesKeys. Refactor SugerenciasWidget para usar el service
  (sin cambio de comportamiento). Tests: 35 (24 service puros + 11 página). Gate verde: services branches 94.67,
  global funcs 79.98; tsc 0, lint limpio. PR# pendiente. NOTA: auditoria ya tenía UI (pages/Core/Auditoria) — no era gap.

[2026-06-24] ✅ agentes frontend PR#230 merged (13 apps).
[2026-06-24] ✅ integracion_b2b frontend completo (configuración, mapeo de campos, logs). Backend ya 100%.
  (El frontend ya existía sin commitear en el worktree desde el inicio de sesión; verificado contra contrato y
  gateado). Agregado: IntegracionB2bPage (Tabs: Configuraciones CRUD, Mapeo de campos CRUD filtrable, Logs
  solo-lectura con StatusChip de estado), integracionB2bService (3 sub-servicios con toList; credenciales_json
  no se loguea, R-CODE-8), rutas+nav 'Integración B2B', integracionB2bKeys. Tests: 44 (28 service puros + 16
  página). Gate verde: services branches 94.24, global funcs 80.03, 1501 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] ✅ integracion_b2b frontend PR#231 merged (14 apps).
[2026-06-24] ✅ personalizacion frontend completo (DSL de personalización, versiones/activar/historial) — ÚLTIMO gap.
  Backend ya 100% (configuraciones + activa/activar/historial). Agregado: PersonalizacionPage (panel de config
  activa, historial de versiones con Activar=rollback gated, crear nueva versión con editor config_yaml + config_dict
  JSON validado, detalle yaml/json), personalizacionService (getAll/historial/activa[404→null]/CRUD/activar con toList),
  rutas+nav 'Personalización', personalizacionKeys. Tests: 38 (24 service puros + 14 página). Gate verde: services
  branches 94.35, global funcs 80.11, 1537 tests; tsc 0, lint limpio. PR# pendiente.

[2026-06-24] 🎉 DONE — Barrido de gaps de FRONTEND completo. Toda app del backend con router HTTP tiene ahora
  frontend funcional (página + servicio + tests vitest + E2E Playwright). 15 módulos construidos esta sesión
  (#215-#232) + fix de E2E (#226). auditoria ya tenía UI (pages/Core/Auditoria). Únicos prefijos sin UI: infra
  (/docs, /redoc, /health) — correcto.
  Módulos: crm, proveedores, gastos, despacho, costos, control_asistencia, servicio_cliente, gestion_aprobaciones,
  gestion_documental, notificaciones, banca_electronica, migracion_datos, agentes, integracion_b2b, personalizacion.
  Disciplina aplicada: PRs focales a develop, automerge con CI verde, cobertura services branches ≥86 / global funcs ≥77
  verificada nativo en worktree con el comando exacto de CI, toList en todo fetch de lista (evita crash con datos
  paginados reales). Deuda menor pendiente: estabilizar OperacionesCambio.test.tsx (flaky timeout 5s, no bloquea CI).
  Siguiente fase sugerida: profundizar paridad por módulo vs Odoo + flujos cruzados entre módulos + más E2E de negocio.

## Fase 2 — Flujos de negocio cruzados (E2E) 2026-06-24

[2026-06-24] ✅ E2E Compra Completa (procure-to-pay) PR#234 merged — CI verde. compras→inventario→CxP→finanzas→
  contabilidad por UI (la UI del flujo ya existía completa). Verifica stock↑, CxP nace y se paga (PAGADA), balance cuadra.
[2026-06-24] ✅ Producción Completa (produce-to-cost) — manufactura→inventario→costos→contabilidad. CERRÓ GAPS de UI:
  faltaba crear orden de producción (nueva OrdenProduccionFormPage) y consumir-materiales (acción+diálogo). +E2E
  produccion-completa.flow (crear OF→consumir [stock MP↓]→avanzar etapas→completar [PT↑]→costo persistido, balance).
  manufacturaService +crearOrden/consumirMateriales/getListasMateriales, schemas, i18n es. Gate verde: 1540 tests,
  services branches 97.87, tsc 0, lint limpio. Strings verificados vs es.json. PR# pendiente.

[2026-06-27] ✅ Producción Completa PR#235 merged (cerró gaps de UI manufactura + E2E). CI verde.
[2026-06-27] ✅ Nómina Completa (hire-to-pay) — rrhh→nomina→contabilidad. Cerró gaps de UI: aprobar proceso,
  aprobar recibo, marcar recibo pagada (acciones gated en ProcesoNominaDetailPage). nominaService +aprobarProceso/
  aprobarRecibo/marcarReciboPagada (+tests actualizados, i18n es+en). E2E nomina-completa.flow (período→proceso→
  procesar [genera recibos]→aprobar→recibos→marcar pagada; devengados/deducciones/neto>0, asiento balanceado vía API).
  Gate: tsc 0, lint limpio, 1546 tests verdes (solo flaky OperacionesCambio ajeno timeout 5s). Strings vs es.json. PR# pendiente.

[2026-06-27] ✅ Nómina Completa PR#236 merged (cerró acciones aprobar/marcar-pagada + E2E). CI verde.
[2026-06-27] ✅ Tesorería: Cambio de Divisa + Conciliación Bancaria — tesoreria→finanzas→contabilidad. BUG REAL
  encontrado y corregido: OperacionCambioFormPage leía campos inexistentes del serializer (m.id_moneda/mp.id en
  vez de moneda/mp.metodo_pago) → selectores rotos / FK equivocado. Fix form + interfaces de service (compat POS,
  bug latente POS flagged task_53c9590b). +E2E cambio-divisa.flow (movimientos EGRESO/INGRESO por moneda + asiento
  CAMBIO_DIVISA balanceado) y conciliacion-bancaria.flow (crear→conciliar-auto→cerrar, end-to-end por UI). Mocks
  corregidos (OperacionesCambio test ahora estable). Gate: 1547 tests EXIT 0, services branches 97.88, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Tesorería cambio-divisa+conciliación PR#237 merged (bug real form + 2 E2E). CI verde.
[2026-06-27] ✅ Fiscal: Libro de Ventas (compliance VE SENIAT) — fiscal↔ventas. UI ya completa (filtro período,
  tabla base/IVA, KPIs, export TXT). E2E fiscal-libro-ventas.flow: siembra FacturaFiscal EMITIDA con IVA vía API →
  consulta libro por período en UI → verifica fila (nro control, base, IVA) + cruce con TXT SENIAT + KPI IVA. Gate:
  1547 tests EXIT 0, tsc 0, lint limpio. E2E-only (sin cambios de fuente). PR# pendiente.

[2026-06-27] ✅ Fiscal Libro de Ventas PR#238 merged (E2E compliance SENIAT). CI verde.
[2026-06-27] ✅ Gasto Completo — gastos→contabilidad→finanzas. UI ya completa. E2E gasto-completo.flow: registrar
  gasto con detalle de imputación → aprobar (asiento GASTO + GASTO_IVA crédito fiscal, estado Contabilizado) →
  crear reembolso → procesar pago (PAGADO). Helper crearPrereqGasto (cuenta contable + categoría + método pago).
  Verifica cruzado por API (asiento balanceado, reembolso PAGADO). Gate: 1547 tests EXIT 0, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Gasto Completo PR#239 merged (E2E aprobación+asiento+reembolso). CI verde.

## Fase 3 — Profundidad por módulo (acciones backend no surfaceadas) 2026-06-27
Auditoría data-driven (url_path de @actions no referenciados en frontend): la mayoría falsos positivos
(features bajo otro naming). Gaps REALES: ventas listas-precio (importar-masivo) y ventas comisiones (liquidar).

[2026-06-27] ✅ Ventas: Listas de Precio (gap real, antes sin UI). ListasPrecioPage (CRUD listas + drawer de
  precios por producto CRUD inline + Importar CSV vía importar-masivo/postForm), listasPrecioService +
  detallesPrecioService (toList, campos reales: es_referencia/codigo/id_moneda). Tests 30, +E2E listas-precio.flow.
  Gate: 1577 tests EXIT 0, services branches 94.45, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Ventas: Listas de Precio PR#240 merged.
[2026-06-27] ✅ Ventas: Comisiones (gap real, antes sin UI). ComisionesPage (Tabs: Esquemas CRUD + overrides por
  categoría inline; Comisiones devengadas read-only con filtros vendedor/estado + StatusChip + resumen KPIs +
  Liquidar por vendedor/período). comisionesService (esquemas/categorias/comisiones con resumen+liquidar, toList).
  Tests 35, +E2E comisiones.flow. Gate: 1612 tests EXIT 0, services branches 94.38, tsc 0, lint. PR# pendiente.
  Backlog restante (auditoría sub-recursos sin UI, filtrando falsos positivos detalles-*/datafono): compras
  procurement (requisiciones/solicitudes-cotizacion/ofertas-proveedor), rrhh (beneficios/tipos-licencia/licencias),
  manufactura master (centros-trabajo/rutas-produccion), fiscal pagos-parafiscales, finanzas pagos-terceros, inventario consignación/variantes.

[2026-06-27] ✅ Ventas: Comisiones PR#241 merged.
[2026-06-27] ✅ Compras: front de aprovisionamiento (source-to-PO) — gap real, antes sin UI. AprovisionamientoPage
  (Tabs: Requisiciones CRUD+líneas, Solicitudes de Cotización/RFQ CRUD+líneas, Ofertas de Proveedor CRUD+líneas
  filtrable por solicitud; StatusChip de estado). aprovisionamientoService (3 entidades + 3 detalles, toList).
  Backend es CRUD puro (sin endpoints de conversión req→cotización→oferta; documentado). Tests 47, +E2E.
  Gate: 1659 tests EXIT 0, services branches 93.95, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Compras: aprovisionamiento PR#242 merged.
[2026-06-27] ✅ RRHH: Beneficios y Licencias (gap real, antes solo Empleados). BeneficiosLicenciasPage (Tabs:
  Beneficios catálogo CRUD, Asignaciones BeneficioEmpleado, Tipos de Licencia CRUD, Licencias con StatusChip +
  aprobar/rechazar/cancelar vía PATCH de estado). beneficiosLicenciasService (4 entidades + cambiarEstado, toList,
  service 100%). Backend sin @actions (estado escribible). Tests 39, +E2E. Gate: 1698 tests EXIT 0, services
  branches 94.02, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ RRHH Beneficios y Licencias PR#243 merged.
[2026-06-27] ✅ Manufactura: Datos Maestros (gap real, BOM/rutas/centros sin UI; la OF seleccionaba BOM pero no
  había cómo crearlos). DatosMaestrosPage (Tabs: Listas de Materiales/BOM CRUD+componentes inline, Rutas de
  Producción CRUD+pasos inline [centro+operación+secuencia], Centros de Trabajo CRUD). manufacturaMaestrosService
  (3 entidades + 2 detalles + operaciones, toList). Tests 43, +E2E. Gate: 1734 tests EXIT 0, services branches 94.05,
  tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Manufactura: Datos Maestros PR#244 merged.
[2026-06-27] ✅ Inventario: Datos Maestros (gap real). InventarioMaestrosPage (Tabs: Variantes de Producto,
  Conversiones de Unidad de Medida, Stock en Consignación cliente/proveedor). inventarioMaestrosService (4 entidades,
  toList). Gate verificado por orquestador: 1773 tests EXIT 0, services branches 94.13, global funcs 78.48, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Inventario: Datos Maestros PR#245 merged.
[2026-06-27] ✅ Nómina: Conceptos + Extrasalarial (gap real, antes solo Procesos regulares). ConceptosNominaPage
  (CRUD catálogo devengados/deducciones/aporte + filtro por_tipo), NominaExtrasalarialPage (procesos aguinaldo/
  vacaciones/prestaciones/liquidación con workflow procesar→aprobar gated + drawer de recibos con aprobar/marcar_pagada).
  nominaExtrasService (3 entidades + acciones, toList). Tests 31, +E2E. Gate: 1805 tests EXIT 0, services branches
  94.15, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Nómina Conceptos+Extrasalarial PR#246 merged.
[2026-06-27] ✅ Cierre de gaps menores (sweep final, 4 entidades sin UI): almacenes UbicacionesAlmacen (CRUD),
  tesoreria MovimientosInternosFondo (transferencias entre cajas), finanzas PagosTerceros/Zelle (alta+workflow
  abonar/reintegro/anular), fiscal PagosParafiscales/IVSS-INCES-FAOV (alta+workflow pagar/anular). gapsMenoresService
  (4 entidades + acciones, toList). Tests: 51 (28 service + 23 página workflow). Gate: 1854 tests EXIT 0, services
  branches 94.32, global funcs 78.00, tsc 0, lint. PR# pendiente.

[2026-06-27] ✅ Cierre de gaps menores PR#247 merged.

## 🎉 DONE — Loop autónomo completo (Fases 1–3) 2026-06-27
Re-auditoría data-driven (sub-recursos de router sin referencia en frontend) tras el sweep: **0 gaps reales
de entidad**. Todo lo restante es falso positivo: abonos-cxp (modal Abonar inline), consumos/etapas/produccion-
terminada/registros-operacion (runtime dentro del detalle de OF), flujo-documentos (motor interno), cajas-usuario/
ajustes-caja-banco (tablas de asignación/ajuste internas).

Resumen del loop:
- FASE 1 — 15 módulos frontend nuevos (apps que no tenían UI): crm, proveedores, gastos, despacho, costos,
  control_asistencia, servicio_cliente, gestion_aprobaciones, gestion_documental, notificaciones, banca_electronica,
  migracion_datos, agentes, integracion_b2b, personalizacion. (#215–#232) + fix E2E (#226, bug real fetchUsuarios).
- FASE 2 — 7 flujos de negocio cruzados con E2E + corrección de bugs reales: procure-to-pay (#234), produce-to-cost
  (#235, +UI crear OF/consumir), hire-to-pay (#236, +aprobar/marcar-pagada), cambio-divisa+conciliación (#237, bug
  real form), fiscal libro de ventas (#238), gasto completo (#239).
- FASE 3 — 9 cierres de gaps de sub-módulo (auditoría data-driven): ventas listas-precio (#240) y comisiones (#241),
  compras aprovisionamiento/RFQ (#242), rrhh beneficios/licencias (#243), manufactura datos maestros BOM/rutas/centros
  (#244), inventario datos maestros (#245), nómina conceptos/extrasalarial (#246), sweep final 4 entidades (#247).

Estado final: toda app del backend con router HTTP tiene frontend funcional; toda entidad de cara al usuario tiene
UI de gestión; los flujos de negocio críticos (P2P, P2C, H2P, order-to-cash, tesorería/FX, fiscal, gasto) tienen
E2E cross-módulo. Gate verde en cada PR (CI: tsc/eslint/vitest≈1854 + cobertura, pytest backend, E2E Playwright,
seguridad, contract). Deuda menor abierta: estabilizar OperacionesCambio.test.tsx (flaky timeout 5s, task_dd4597a5);
bug latente POS campos legados (task_53c9590b). Siguiente fase posible (incremental, no bloqueante): profundizar
cobertura de tests de páginas pre-existentes con baja cobertura de funciones, y paridad fina de features vs Odoo.

## 🚀 Loop CxC Lubrikca (subproyecto) — arranque 2026-06-27
Fuente de verdad: docs/cxc-lubrikca/PLAN_TRABAJO.md (Fases 0–7). Worktree dedicado
feature/cxc-lubrikca (base 22a9696 + plan 4e4b9eb). App nueva aislada apps/cxc_lubrikca.

[2026-06-27] ✅ Fase 0 — Diseño e integración (commit 2ad6b19). ADR-013 (app dedicada,
  aislamiento estricto solo-lectura del core, Odoo solo lectura, feature-flag perfil cobranza).
  Scaffold apps/cxc_lubrikca registrado en INSTALLED_APPS + /api/cxc-lubrikca/ con health.
  MAPA_DATOS_GAPS.md: gaps del conector Odoo (delivery_status, date_done picking, qty_delivered,
  brand_id, categoria raiz, amount_total_signed_usd, user_id.login) → cierre en Fase 5 por extension.
  Recon previa: motor CxC_Lubrikca (~37 tests puros portables: business_days/effective_dating/
  equivalents/discounts/reconcile/hour_audit), convenciones Omni (uuid7+empresa, get_empresas_visible,
  generar_asiento_o_fallar, pytest cov-fail-under=92). Gate: check + makemigrations --check + 2 tests EXIT 0.

[2026-06-27] ✅ Fase 1 — Config del motor con effective dating (commit 2425719). 6 modelos
  (DescuentoMarcaCategoria, DescuentoBCVCompleto, PromocionPrimeraCompra, ReglaRecurrencia,
  Feriado, MetodoPago) sobre base abstracta CxcLubrikcaBaseModel (uuid7+empresa+soft delete).
  services/effective_dating.py portado (semántica idéntica a CxC_Lubrikca, verificado por review).
  DRF serializers+viewsets multi-tenant (empresa forzada, scope get_empresas_visible, soft delete)
  en /api/cxc-lubrikca/. Review SEC/DIFF/correctness: sin blockers; 3 hardenings aplicados
  (403 sin empresa, valor>=0, test cross-tenant PATCH 404). Gate: check + makemigrations --check +
  33 tests EXIT 0, 100% cobertura del paquete (309 stmts, 0 miss).

[2026-06-27] ✅ Fase 2 — Motor determinístico portado (commit 2c1712b). Port fiel y Django-free a
  services/motor/ (dataclasses propias): business_days, equivalents, effective_dating (canónico),
  discounts.calcular_factura (neto-objetivo/apilamiento/reselección lista/contado ventana/BCV-completo/
  mezcla→Binance/promo/devoluciones D/cierre híbrido), reconcile.clasificar_diferencia, hour_audit,
  price_resolver, decimal_utils, config. Paridad verificada por diff (lógica idéntica al origen).
  61 tests puros EXIT 0 en 1.14s; 100% cobertura motor (565 stmts). Bridge Django/Odoo→dataclasses = Fase 3.

[2026-06-28] ✅ Fase 3 — Captura + bandeja de aprobación (commit da1cb16). Modelos espejo
  (PedidoLubrikca/LineaPedidoLubrikca/PrecioListaLubrikca/PagoLubrikca) + Vinculacion (equivalentes
  congelados, extensión sin tocar AbonoCxC) + BandejaFacturacion. Bridge Django→dataclasses del motor
  (construir_engine_inputs/recalcular_bandeja). Captura registrar_vinculacion (validaciones, estampado de
  tasas por fecha local Caracas, congelado de equivalentes). Aprobación por roles reutilizando
  gestion_aprobaciones. API tenant-scoped; guard precio faltante→400. Review sin blockers (mapeo enum del
  bridge verificado). Gate: check + makemigrations + 135 tests EXIT 0, 100% cobertura app (1340 stmts).

[2026-06-28] ✅ Fase 4 — Conciliación (commit a1bfa9f). ConfiguracionConciliacion (tolerancias/empresa)
  + ConciliacionLubrikca (OneToOne pedido) + PedidoLubrikca.ncs_facturadas. conciliar_pedido usa
  motor.reconcile.clasificar_diferencia (neto USD = monto_facturado − NCs) → semáforo. resumen_cartera
  (tablero DSO/devoluciones/candidatas). API tenant-scoped (conciliar/revisar/resumen). Gate: check +
  makemigrations + 27 tests EXIT 0, 100% archivos nuevos. Odoo poblará facturado/NCs en Fase 5.

[2026-06-28] ✅ Fase 5 — Sync Odoo→espejo solo lectura (commit 9033804). LubrikcaOdooReader (execute
  inyectable, testeable con fakes) + sync que puebla el espejo cerrando gaps (delivery_status, date_done,
  qty_delivered neto, devoluciones, brand_id, raíz categoría, amount_total_signed_usd, NCs, vendedor login).
  Reusa cliente XML-RPC de integration_hub por composición (cero cambios al core, cero escritura Odoo);
  nunca toca Vinculacion/Bandeja/Conciliacion. Command + acción API. Gate: check + makemigrations + 39 tests
  EXIT 0 (sync 97.7%, reader 99.4%). Aislamiento verificado. Limitación: precios lista 4/5 (Odoo18 sin price_get).

[2026-06-28] ✅ Fase 6a — Frontend cobranza: fundación + Dashboard + Config del Motor (commit 17a65ef).
  cxcLubrikcaService (todos los endpoints), cxcLubrikcaKeys, schemas zod (decimal.js), wiring (perfil
  cobranza + nav + rutas gated). Páginas: DashboardCxcLubrikca (KPIs resumen + sincronizar Odoo),
  ConfigMotor (tabs CRUD de 7 entidades). Gate: tsc + lint + test:coverage verde (umbrales globales/carpeta).
[2026-06-28] ✅ Estabilización tests dependientes de fecha/tiempo (commit f071456). PagosTercerosPage
  (fecha hoy → validar formato ISO) + OperacionesCambio (timeout 15s en 2 tests con userEvent, deuda
  conocida task_dd4597a5). Necesario para CI verde del PR final. Fase 6b en curso (captura/bandeja/
  conciliación/cartera).

[2026-06-28] ✅ Fase 6b — Frontend captura/bandeja/conciliación/cartera (commit eddbe63). 4 páginas MUI
  (CapturaPage: pedidos+recalcular+vincular pago; BandejaPage: proponer/confirmar cierre híbrido;
  ConciliacionPage: semáforo+conciliar+revisar+KPIs; CarteraPage: devoluciones+DSO). Gate: tsc+lint+
  test:coverage verde (2008 tests). Frontend cobranza completo. Inicia Fase 7 (gate final + PR a develop).

[2026-06-28] ✅ Fase 7 — Preparación a producción. CHECKLIST_GO_LIVE.md (config a cargar, conector Odoo
  D2, sincronización, smoke tests, validación contra Odoo real). PLAN_TRABAJO.md actualizado (DoD).
  Pasos que requieren acceso a producción (cargar config real, validar Odoo real) → acción del OWNER.
  Pendiente: push rama + PR a develop + automerge con CI verde.

[2026-06-28] PR #256 a develop — 1ª corrida CI: 3 fallos diagnosticados y corregidos:
  - Backend: `mapa_superficie --check` (la app nueva añadió superficie) → regeneradas matrices A1.
  - Contract: drf_yasg SwaggerGenerationError por colisión de ref_name MetodoPago con finanzas →
    ref_name explícito 'CxcLubrikcaMetodoPago'.
  - E2E: fallos pre-existentes (cambio-divisa/comisiones/compra-completa) por base stale (rama nacía
    21 commits atrás de develop) → merge de origin/develop (trae fix asegurarMoneda en e2e/helpers/datos.ts).
  Re-push (merge e84c9a3 + fix 14824d9); 2ª corrida CI en curso.

[2026-06-28] PR #256 — 2ª corrida CI: Contract ✅, Frontend ✅, Static ✅, Security ✅, Agent Eval ✅.
  Backend ❌ por gate RLS (test_rls_rollout): las 14 tablas tenant nuevas necesitaban RLS → añadidas a
  apps/core/rls.py RLS_TABLES + migración 0004_rls_cxc_lubrikca (política omni_rls_tenant, columna empresa_id,
  null_visible=False). Verificado local: test_rls_rollout 162 passed; suite cxc_lubrikca 201 passed con RLS forzado.
  E2E ❌: fallo PRE-EXISTENTE de develop (su propia CI está roja en E2E hoy 2026-06-28); 11 specs de módulos
  ajenos (cambio-divisa/comisiones/compra-completa/nómina/manufactura/etc.), CERO specs de cxc_lubrikca →
  no atribuible a este PR; bloqueo repo-wide para ESCALACIÓN al owner.

[2026-06-28] ⚠️ ESCALATION — PR #256 listo, bloqueado por E2E repo-wide.
  3ª corrida CI: TODOS los checks atribuibles al PR en VERDE (Backend ✅ con RLS, Contract ✅, Frontend ✅,
  Static ✅, Security ✅, Agent Eval ✅, Railway deploys ✅). ÚNICO rojo: E2E (BLOQUEANTE).
  Diagnóstico: 13 specs E2E fallan, TODAS de módulos ajenos (incl. login-multiempresa y venta — base) y
  CERO de cxc_lubrikca. La CI de develop está roja en E2E hoy (mismo patrón). El fallo de login-multiempresa
  implica que el setup de sesión/seed de E2E está roto a nivel repo, no por este PR.
  No se hace merge: la política exige CI verde y E2E es BLOQUEANTE; arreglar 13 flujos E2E ajenos excede el
  alcance de cxc-lubrikca y la causa raíz (seed/auth/entorno E2E en develop) es del owner.
  ENTREGADO: subproyecto CxC Lubrikca Fases 0-6 100% (11 commits), PR #256, todo lo propio verde.

[2026-06-28] Diagnóstico E2E refinado (debida diligencia tras hook): login-multiempresa y venta NO son
  regresiones del PR — son FLAKY pre-existentes en develop. Evidencia: en 4 corridas E2E de develop,
  login-multiempresa falla en 1/4 (run 28311404370); develop NO tiene mis cambios. LoginPage.tsx (que
  renderiza 'Selecciona empresa y sucursal') no fue tocado y está fuera del layout autenticado que sí
  modifiqué. Conclusión firme: 0 specs cxc_lubrikca fallan; el PR no introduce regresiones E2E; el job
  E2E es inestable + tiene 11 specs rotos de forma consistente en develop (módulos ajenos). El merge
  sigue bloqueado por causa repo-wide ajena al PR → ESCALATION se mantiene (decisión del owner).

[2026-06-28] 🎉 DONE — PR #256 MERGEADO a develop (merge commit 837e270, override de admin autorizado
  explícitamente por el owner ante el bloqueo E2E repo-wide ajeno al PR). Subproyecto CxC Lubrikca
  completo: Fases 0–7, app aislada apps/cxc_lubrikca (config motor + motor determinístico + captura/
  bandeja + conciliación + sync Odoo read-only + RLS), frontend cobranza (6 pantallas MUI). Todos los
  checks propios verdes (Backend incl. RLS, Contract, Frontend, Static, Security). Go-live (config real +
  validación Odoo real) = acción del owner por CHECKLIST_GO_LIVE.md. Railway auto-despliega develop a staging.

[2026-06-28] ✅ Seguimiento — Sync programado (PLAN Fase 5 "Sync programado"). apps/cxc_lubrikca/tasks.py:
  cxc_lubrikca.sync_todos (fan-out a tenants Mode-A datasource=odoo) + cxc_lubrikca.sync (por empresa,
  tolerante a fallos). Reusa la infra D2/Celery; el cronograma se registra vía django-celery-beat (ops,
  documentado en CHECKLIST_GO_LIVE.md). Rama feature/cxc-lubrikca-sync-beat desde develop (post-merge #256).
  Gate: check + makemigrations + 4 tests EXIT 0, tasks.py 100%.
