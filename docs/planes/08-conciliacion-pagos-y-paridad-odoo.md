# Plan 08 — Conciliación N:M de Pagos y Paridad ERP estilo Odoo

> Plan de ejecución técnico derivado de [`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md)
> y [`docs/integracion-hub/ESTADO.md`](../integracion-hub/ESTADO.md).
> Conserva intactos los diferenciales de Omni ERP (**AI-Native REST + MCP**, **multimoneda y doble tasa VE**,
> **modo sin fricción para empresas informales**) y alinea sus módulos incompletos con la arquitectura
> probada de Odoo (`account.partial.reconcile`, `account.journal`, procurement, `orderpoint`).

| Campo | Valor |
|---|---|
| **Estado** | Bloque A COMPLETADO (`PR #297`, `PR #298`, Ola A3); Bloque B §B.1 (`contabilidad` Olas B1 + B2) + §B.2 (`compras` + `gestion_aprobaciones` Ola B3) COMPLETADO |
| **Fecha** | 2026-11-17 (basado en símbolos verificados en `origin/develop @ ff2bdb6`) |
| **Apps involucradas** | `finanzas`, `core`, `cuentas_por_cobrar`, `cuentas_por_pagar`, `ventas`, `compras`, `contabilidad`, `gestion_aprobaciones`, `inventario`, `almacenes`, `banca_electronica`, `tesoreria`, `integration_hub`, `agentes` |
| **Esfuerzo estimado** | ~5–7 semanas en PRs pequeños y focales (`R-PROC-2`) |

---

## Bloque A — Conciliación N:M Pagos ↔ Facturas/Obligaciones anclada en `core.Contacto`

### A.1 Diagnóstico actual (verificado en código)

Hoy `finanzas.Pago` (`backend/apps/finanzas/models.py`) modela un único destino por registro mediante `tipo_documento` + `id_documento` (UUID único) y FKs sueltas (`id_factura`, `id_cxp`, `id_pedido`, `id_nota_venta`, etc.). Esto genera tres limitaciones críticas frente al flujo real de caja y frente a `account.partial.reconcile` de Odoo:

1. **Un pago no puede repartirse entre N obligaciones/facturas:** si un cliente transfiere \$100 para saldar \$35 restantes de una factura vencida y abonar \$65 a una nueva, hoy no existe estructura N:M que registre ambas imputaciones sobre el mismo `Pago`.
2. **Sin manejo nativo de anticipos / saldos a favor:** el excedente no aplicado de un `Pago` no queda trazado como crédito disponible del `Contacto` para futuras conciliaciones.
3. **Bloqueo en `Integration Hub` ([`ESTADO.md`](../integracion-hub/ESTADO.md) §4.1):** `_upsert_pago` hoy solo puede importar cobros de Odoo reconciliados con *exactamente una* factura y descarta cobros multi-factura y pagos outbound a proveedor.

### A.2 Modelo canónico `finanzas.AsignacionPago`

Inspirado en `account.partial.reconcile` de Odoo y adaptado a las convenciones de Omni (§3.3 del Plan Maestro, sin `ContentType`):

- **Ubicación:** `backend/apps/finanzas/models.py` (hereda de `OmniBaseModel`, PK `id_asignacion = UUIDField(primary_key=True, default=uuid7)`).
- **Aislamiento y RLS:** `id_empresa = ForeignKey("core.Empresa", on_delete=models.CASCADE)`. Registrar `finanzas_asignacion_pago` en `apps/core/rls.py` (`RLS_TABLES`) con migración reversible `FORCE ROW LEVEL SECURITY`.
- **Ancla de identidad:** `id_contacto = ForeignKey("core.Contacto", on_delete=models.PROTECT, related_name="asignaciones_pago")` (y agregar `id_contacto` nullable en `finanzas.Pago` con backfill desde `crm.Cliente.contacto` / `proveedores.Proveedor.contacto`).
- **Origen:** `id_pago = ForeignKey("finanzas.Pago", on_delete=models.PROTECT, related_name="asignaciones")`.
- **Destino polimórfico tipado:**
  - `tipo_documento`: `CUENTA_POR_COBRAR` (`cuentas_por_cobrar.CuentaPorCobrar`), `CUENTA_POR_PAGAR` (`cuentas_por_pagar.CuentaPorPagar`), `FACTURA_VENTA` (`ventas.FacturaFiscal`), `FACTURA_COMPRA` (`compras.FacturaCompra`).
  - `id_documento`: `UUIDField(db_index=True)`.
  - FKs opcionales para joins sin N+1 e integridad referencial: `id_cxc`, `id_cxp`, `id_factura_venta`, `id_factura_compra` (un `CheckConstraint` o `clean()` garantiza correspondencia exacta entre `tipo_documento`, `id_documento` y la FK concreta).
- **Montos y tasas (`R-CODE-4`, `Decimal` siempre):**
  - `monto_asignado_pago`: `DecimalField(max_digits=18, decimal_places=4)` — porción del `Pago` consumida en la moneda del `Pago`.
  - `monto_asignado_documento`: `DecimalField(max_digits=18, decimal_places=4)` — monto aplicado en la moneda de la obligación/factura destino.
  - `id_moneda_documento`: FK `finanzas.Moneda`.
  - `tasa_aplicada`: `DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"))`.
  - `diferencia_cambiaria`: `DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))` + `tipo_diferencia` (`""` | `"GANANCIA"` | `"PERDIDA"`).
- **Trazabilidad y reversibilidad (`R-CODE-6`, `R-PROD-4`, `R-CODE-11`):**
  - `estado`: `ACTIVA` | `REVERTIDA`.
  - `fecha_aplicacion`: `DateTimeField(default=timezone.now)`.
  - `fecha_reversion`: `DateTimeField(null=True, blank=True)`.
  - `motivo_reversion`: `CharField(max_length=255, blank=True, default="")`.
  - `id_asiento`: FK nullable a `contabilidad.AsientoContable` (`on_delete=models.SET_NULL`).
  - `id_usuario_registro`: FK nullable a `core.Usuarios`.
  - `referencia_externa`: `CharField(max_length=100, blank=True, default="")` (para trazabilidad con `account.partial.reconcile` de Odoo).
- **Constraints en BD:**
  - `CheckConstraint(monto_asignado_pago__gt=0)` y `CheckConstraint(monto_asignado_documento__gt=0)`.
  - Índice compuesto `(id_empresa, id_contacto, estado)` y `(id_empresa, tipo_documento, id_documento, estado)`.

### A.3 Reglas de negocio y atomicidad (`apps/finanzas/services_conciliacion_pagos.py`)

Toda operación corre dentro de `@transaction.atomic` adquiriendo locks en orden determinístico por PK (`select_for_update()`) sobre el `Pago` y los documentos destino:

1. **Regla 1 → N y N → 1:**
   - Un mismo `Pago` puede fraccionarse en N `AsignacionPago` (p. ej. saldar el remanente de una obligación antigua y abonar parcial o totalmente otras obligaciones abiertas del **mismo `core.Contacto`** dentro de la **misma `id_empresa`**).
   - Una misma obligación (`CuentaPorCobrar`, `CuentaPorPagar`, `FacturaFiscal`, `FacturaCompra`) puede recibir M `AsignacionPago` de múltiples pagos hasta completar su saldo.
2. **Validación estricta de topes:**
   - `sum(asignaciones ACTIVAS del pago) <= pago.monto`.
   - `sum(asignaciones ACTIVAS del documento) <= saldo_aplicable_documento` (cualquier excedente queda sin asignar en el `Pago`, nunca sobre-aplica la factura).
   - Validación cross-tenant y de identidad obligatoria:
     - Utilizar un helper polimórfico `_extraer_empresa_id(documento)` (análogo a `_extraer_empresa` en `apps/contabilidad/services.py:105`): `cuentas_por_pagar.CuentaPorPagar`, `ventas.FacturaFiscal` y `compras.FacturaCompra` usan `id_empresa_id`, mientras `cuentas_por_cobrar.CuentaPorCobrar` usa `empresa_id` **nullable** (`ADR-009`). Si `_extraer_empresa_id(documento)` retorna `None`, la operación falla cerrado (fail-closed) y siempre exige `pago.id_empresa_id == _extraer_empresa_id(documento) == contacto.id_empresa_id`.
     - Validación del `id_contacto` común: para documentos con `crm.Cliente` o `proveedores.Proveedor` se resuelve vía su `OneToOneField` a `core.Contacto` (exigiendo que exista o enlazándolo primero). Si una `CuentaPorCobrar` proviene de fuente externa sin `crm.Cliente` (`cliente=None` y `cliente_externo_id` poblado, `ADR-009`), el servicio resuelve el `core.Contacto` por el mapa `EntidadSincronizada` / coincidencia normalizada en la misma empresa antes de conciliar; si no existe `Contacto` resuelto o difiere del `id_contacto` del `Pago`, rechaza la asignación con error de dominio (`400`/`422`).
3. **Saldo a favor / anticipo del contacto:**
   - Todo `Pago` (o remanente `pago.monto - sum(asignaciones ACTIVAS.monto_asignado_pago) > 0`) pertenece al `id_contacto` y queda disponible como **anticipo / saldo a favor** (`INGRESO` para clientes, `EGRESO` pagado por adelantado para proveedores).
   - Endpoint y helper `saldo_a_favor_contacto(empresa, contacto, tipo_operacion)` calculado en BD con `Sum`/`Coalesce`, aplicable a futuras facturas/obligaciones sin crear `Pago` duplicado.
4. **Diferencial cambiario y asiento automático (`R-CODE-11`):**
   - Cuando la moneda del `Pago` difiere de la moneda de la obligación o la tasa de liquidación difiere de la tasa de emisión (reutilizando `TasaCambio` y el patrón existente de `cuentas_por_pagar.DiferenciaCambiaria`), calcula `diferencia_cambiaria` en moneda base.
   - Genera los asientos automáticos (`PAGO_CXC` / `PAGO_CXP` + `GANANCIA_CAMBIARIA` / `PERDIDA_CAMBIARIA`, y reclasificación desde cuenta puente de anticipos si aplica) en la **misma `@transaction.atomic`** cuando `empresa.contabilidad_activa=True` o exista `MapeoContable`.
   - En documentos importados *history-only* desde Odoo, la asignación puede marcarse `generar_asiento=False` de forma explícita y controlada para no duplicar contabilidad histórica.
5. **Actualización sincronizada de saldos y estados:**
   - Al aplicar o revertir una asignación, se actualizan atómicamente los saldos y estados de la obligación destino (`CuentaPorCobrar`: `pendiente`→`parcial`→`pagada`; `CuentaPorPagar`: `PENDIENTE`→`PARCIAL`→`PAGADA`; `FacturaFiscal`: `EMITIDA`→`PAGADA`) y se sincroniza el vínculo con `AbonoCxC` / `AbonoCxP` cuando corresponda para no romper reportes ni aging existentes.
6. **Reversión controlada (`R-PROD-4`):**
   - `revertir_asignacion_pago(asignacion, usuario, motivo)` marca `estado='REVERTIDA'`, `activo=False`, restaura el saldo de la obligación, libera el saldo en el `Pago` y emite contra-asiento contable si había `id_asiento`.

### A.4 API REST, MCP (`R-CODE-7`) y Frontend

- **REST (`apps/finanzas/`):**
  - `AsignacionPagoViewSet` (`BaseModelViewSet`, `http_method_names = ["get", "post", "head", "options"]`): bloquea `PUT`/`PATCH`/`DELETE` libres (espejo del guard P0 de CxC/CxP); la creación delega en `aplicar_pago_a_documentos(...)` y la reversión usa `@action(detail=True, methods=["post"]) revertir`.
  - `@action` en `PagoViewSet`: `conciliar-documentos` (aplica un pago a 1..N documentos en lote atómico) y `sugerir-distribucion` (propuesta FIFO por vencimiento más antiguo para el `Contacto`).
  - Endpoint `GET /api/finanzas/contactos/<id_contacto>/estado-conciliacion/` (pagos con saldo disponible + obligaciones pendientes + anticipo neto).
- **MCP (`apps/finanzas/mcp.py`, `R-CODE-7`):**
  - `finanzas_get_saldos_favor_contacto` (`finanzas:read`).
  - `finanzas_conciliar_pago_multiple` (`finanzas:write`).
  - `finanzas_revertir_asignacion_pago` (`finanzas:write`).
- **Frontend (MUI v7 + TanStack Query + `decimal.js`):**
  - Componente reutilizable `ConciliacionContactoDialog` / página dedicada accesible desde **CxC**, **CxP** y **Tesorería** (`PropuestaConciliacionBancaria`): muestra pagos del contacto con saldo disponible arriba, obligaciones abiertas abajo, auto-reparto FIFO con ajuste manual por fila (`decimal.js`) y resumen de diferencial cambiario + saldo a favor resultante.

---

## Bloque B — Paridad ERP estilo Odoo en módulos incompletos

> **Regla de diseño:** cada mejora conserva los diferenciadores de Omni — modo sin fricción (`contabilidad_activa=False`), doble tasa BCV/real, capacidades AI-Native (REST + MCP) y arquitectura modular multi-tenant con RLS.

### B.1 `contabilidad` — Diarios, Reversión por Contra-asiento, Cierre y Reportes Canónicos ✅ COMPLETADO (`PR #300` + `PR-14`)

**Estado actual verificado (`apps/contabilidad/`):** existen `PlanCuentas`, `AsientoContable`, `DetalleAsiento`, `MapeoContable`, `generar_asiento()` (`R-CODE-11`) y un `balance_comprobacion` básico en `views.py:115` que carga filas en Python y no filtra por fechas. `anular()` (`views.py:101`) muta `estado_asiento="ANULADO"` sin generar contra-asiento.

**Entregables incrementales:**
1. **Preservación de empresas informales:** si `Empresa.contabilidad_activa=False`, ningún flujo operativo obligatorio bloquea ventas/compras/caja; los modelos nuevos son opcionales o auto-provisionados.
2. **`DiarioContable` (`contabilidad_diario`, estilo `account.journal`):**
   - Tipos: `VENTAS`, `COMPRAS`, `BANCO`, `CAJA`, `NOMINA`, `VARIOS`.
   - Campos: `codigo` (único por empresa), `nombre`, `tipo`, `prefijo_secuencia`, `siguiente_numero`, `cuenta_defecto_debe`, `cuenta_defecto_haber`, `id_cuenta_bancaria` (nullable → `finanzas.CuentaBancariaEmpresa`), `id_caja` (nullable → `finanzas.Caja`), `activo`.
   - Enlace opcional `AsientoContable.id_diario` y `MapeoContable.id_diario` (fallback al diario por defecto según `tipo_asiento`).
3. **Reversión atómica por contra-asiento:**
   - Agregar `AsientoContable.asiento_revertido = OneToOneField("self", null=True, blank=True, related_name="contra_asiento")` y `DetalleAsiento.id_contacto = ForeignKey("core.Contacto", null=True, blank=True)` (para mayor auxiliar por tercero).
   - Servicio `revertir_asiento(asiento, *, usuario, fecha_reversion=None, motivo="")` en `@transaction.atomic`: para asientos `APROBADO`, en lugar de sobrescribir el historial, crea un contra-asiento `APROBADO` con `debe`/`haber` invertidos, bloqueando doble reversión (idempotente / 400 si ya fue revertido). `BORRADOR` puede seguir anulándose sin contra-asiento.
4. **`PeriodoContable` (`contabilidad_periodo_contable`) y cierre de ejercicio:**
   - Estados `ABIERTO` | `CERRADO` por `(id_empresa, anio, mes)` y cierre anual.
   - `generar_asiento()` y `aprobar()` validan que el período contable esté `ABIERTO` (coordinado con `fiscal.validar_periodo_abierto`).
   - Servicio `cerrar_ejercicio_contable(empresa, anio, cuenta_resultado_acumulado, usuario)` en `@transaction.atomic`: salda cuentas de `INGRESO`, `COSTO` y `GASTO` contra la cuenta de resultado en `PATRIMONIO` y cierra los períodos del ejercicio.
5. **Reportes financieros canónicos (agregación PostgreSQL + UI + PDF ReportLab + CSV + doble USD):**
   - `GET /api/contabilidad/reportes/balance-comprobacion/` (rango de fechas, saldo inicial, débitos, créditos, saldo final, jerarquía `PlanCuentas`, parámetro `incluir_equivalentes_usd=true`).
   - `GET /api/contabilidad/reportes/estado-resultados/` (P&L: Ingresos − Costos − Gastos = Resultado Neto).
   - `GET /api/contabilidad/reportes/balance-general/` (Activos = Pasivos + Patrimonio + Resultado del período).
   - `GET /api/contabilidad/reportes/libro-mayor-auxiliar/` (filtrado por `id_cuenta_contable`, `id_contacto`, `id_diario` y rango de fechas, con saldo corrido).
   - Tools MCP (`contabilidad:read`) + páginas MUI en `/contabilidad/reportes/*` y `/contabilidad/diarios`.

---

### B.2 `compras` + `gestion_aprobaciones` — Flujo Transaccional Source-to-PO y Reglas Avanzadas — ✅ COMPLETADO (PR-15)

**Estado actual verificado:** `compras/models.py` ya define `RequisicionCompra`, `SolicitudCotizacion` (RFQ), `OfertaProveedor` y `OrdenCompra`, con CRUD/UI en `AprovisionamientoPage` (`#242`), pero `compras/services.py` solo tiene `aprobar_orden_compra`, `registrar_recepcion` y `registrar_factura_compra`. Por su lado, `gestion_aprobaciones/services.py` ya implementa `evaluar_etapas`, `crear_solicitud` y `registrar_decision` (por monto, rol o usuario), pero carece de reglas por departamento, SLA/escalación y cobertura transversal completa.

**Entregables incrementales:**
1. **Capa transaccional `compras/services_procurement.py` (`@transaction.atomic` + `select_for_update`):**
   - `enviar_requisicion_aprobacion(requisicion, usuario)`: cambia `BORRADOR → PENDIENTE` y dispara `gestion_aprobaciones.crear_solicitud(..., codigo_tipo="REQUISICION_COMPRA", monto=total_estimado)`.
   - `crear_rfq_desde_requisiciones(empresa, requisicion_ids, proveedores_ids, fecha_vencimiento, usuario)`: consolida líneas de requisiciones `APROBADA` en una `SolicitudCotizacion` (`ENVIADA`), con trazabilidad a las requisiciones origen (`id_requisicion` / enlace).
   - `adjudicar_oferta_a_orden_compra(oferta, almacen_destino, usuario, adjudicacion_parcial=None)`: valida `SolicitudCotizacion` abierta, marca la `OfertaProveedor` ganadora como `ACEPTADA` (y opcionalmente las competidoras como `RECHAZADA`), crea `OrdenCompra` + `DetalleOrdenCompra` en `BORRADOR` (o la pasa por aprobación si supera umbral) y actualiza la `RequisicionCompra` a `PROCESADA`.
2. **Motor avanzado en `gestion_aprobaciones`:**
   - Extender `FlujoAprobacion` con `id_departamento` nullable (`core.Departamento`), `sla_horas` (`PositiveIntegerField(null=True, blank=True)`) y `escalar_a_rol`/`escalar_a_usuario`.
   - Actualizar `evaluar_etapas(empresa, codigo_tipo, monto, departamento=None)` para priorizar flujos del departamento y caer al flujo general si `departamento is None`.
   - Tarea Celery periódica `gestion_aprobaciones.escalar_solicitudes_vencidas` que notifica (`core.Notificacion`) o reasigna etapa vencida según SLA.
   - Conectar aprobaciones opcionales (configurables por `TipoAprobacion`) en `RequisicionCompra`, `finanzas.PagoTercero`, `tesoreria.OperacionCambioDivisa` y acciones de agentes `Omni Connect S12`.
3. **UI + MCP:**
   - Comparativo de ofertas lado a lado en `AprovisionamientoPage` + botones transaccionales ("Enviar a aprobación", "Generar RFQ", "Adjudicar → Orden de Compra").
   - Tools MCP `compras_crear_requisicion`, `compras_adjudicar_oferta`, `aprobaciones_pendientes`, `aprobaciones_decidir`.

---

### B.3 `inventario` + `almacenes` — Reabastecimiento Automático, Lotes Opt-in y Ubicaciones

**Estado actual verificado:** `inventario` ya tiene `ValoracionInventario` (FIFO/Promedio), COGS, `PasoOperacion`/`OperacionInventario` y `ReordenSugeridorAgent`; `almacenes` tiene `Almacen` y `UbicacionAlmacen` con CRUD/UI (`#247`), pero sin stock desagregado por ubicación ni reglas formales de reabastecimiento ni trazabilidad de lotes/vencimientos.

**Entregables incrementales:**
1. **`ReglaReabastecimiento` (`inventario_regla_reabastecimiento`, estilo `stock.warehouse.orderpoint`):**
   - Campos: `id_empresa`, `id_producto`, `id_variante` (nullable), `id_almacen`, `stock_minimo`, `stock_maximo`, `cantidad_multiplo` (`Decimal(18, 4)`), `ruta` (`COMPRA` | `MANUFACTURA` | `TRANSFERENCIA`), `id_proveedor_preferido` (nullable → `proveedores.Proveedor`), `id_almacen_origen` (nullable, para ruta `TRANSFERENCIA`), `activo`.
   - Unicidad activa `(id_empresa, id_producto, id_variante, id_almacen)`.
   - Servicio `evaluar_reabastecimiento(empresa, almacen=None)` que calcula `deficit` considerando `cantidad_disponible - cantidad_comprometida + cantidad_en_transito`, integrado con `ReordenSugeridorAgent` y acción para generar borrador de `compras.RequisicionCompra` o `manufactura.OrdenProduccion` según `ruta`.
2. **Trazabilidad opt-in de `LoteProducto` (`inventario_lote_producto`):**
   - Reutilizar **`Producto.maneja_lotes`** (y respetar el existente `Producto.maneja_seriales` en `backend/apps/inventario/models.py:60-61`, sin duplicar campos booleanos) añadiendo solo `Producto.estrategia_salida = CharField(choices=[("FIFO", "FIFO"), ("FEFO", "FEFO")], default="FIFO")`: **comercios simples mantienen `maneja_lotes=False` y operan sin fricción (`R-PROD-3`)**.
   - Modelo `LoteProducto`: `id_empresa`, `id_producto`, `id_variante`, `id_almacen`, `numero_lote` (único por `(id_empresa, id_producto, numero_lote)`), `fecha_fabricacion`, `fecha_vencimiento`, `cantidad_disponible`, `cantidad_reservada`, `activo`.
   - Integración en el chokepoint `registrar_movimiento()` (`inventario/services.py`): si `producto.maneja_lotes=True`, exige `lote` en entradas o selecciona automáticamente por FEFO/FIFO en salidas atómicas (`select_for_update`).
3. **Transferencias y reservas por `UbicacionAlmacen` (`almacenes`):**
   - `Almacen.usa_ubicaciones = BooleanField(default=False)` (opt-in para bodegas simples).
   - `StockUbicacion` (`almacenes_stock_ubicacion`): `(id_empresa, id_almacen, id_ubicacion, id_producto, id_variante)` con `cantidad_disponible` y `cantidad_reservada`.
   - Servicios `@transaction.atomic`: `transferir_entre_ubicaciones(...)` (valida `requiere_autorizacion` de `UbicacionAlmacen` y registra movimiento interno) y `reservar_ubicacion(...)`.
4. **UI + MCP:**
   - Tabs en `InventarioMaestrosPage` / `Almacenes` para reglas de reabastecimiento, lotes con alerta de vencimiento próximo y transferencias entre ubicaciones; tools MCP `inventario_evaluar_reabastecimiento`, `inventario_consultar_lotes`.

---

### B.4 `banca_electronica` + `Integration Hub` — Consolidación Bancaria, `facturas_compra` y `CTF-011`

**Estado actual verificado:**
- `apps/banca_electronica/models.py` define `CuentaBancariaEmpresa` (`empresa`, `banco`, `numero_cuenta`, `tipo_cuenta`, `moneda`, `saldo_actual`, `activa`), que **duplica** `finanzas.CuentaBancariaEmpresa` (`id_cuenta_bancaria`, `id_empresa`, `nombre_banco`, `numero_cuenta`, `id_moneda`, `metodos_pago`, `monedas`), siendo esta última la única usada por `Pago`, `MovimientoCajaBanco`, `ConfiguracionConciliacionCuenta` y `PropuestaConciliacionBancaria` (`tesoreria` PRs `#283–#284`).
- `docs/integracion-hub/ESTADO.md` §4.1 mantiene pendientes: (1) `facturas_compra` inbound, (2) pagos multi-factura y pagos outbound a proveedor, y (3) push outbound a Odoo (`CTF-011`).

**Entregables incrementales:**
1. **Consolidación `banca_electronica` ↔ `finanzas` ↔ `tesoreria`:**
   - Designar **`finanzas.CuentaBancariaEmpresa`** como **único maestro canónico** de cuentas bancarias de la empresa.
   - Migrar los datos residuales de `banca_electronica_cuentabancariaempresa` hacia `finanzas_cuenta_bancaria_empresa` (migración reversible con `id_cuenta_bancaria` mapeado) y reemplazar `banca_electronica` en una capa de servicios operativos bancarios sobre `finanzas.CuentaBancariaEmpresa` y `tesoreria.ExtractoBancarioArchivo` / `PropuestaConciliacionBancaria`:
     - Generador de archivos de lotes de pago bancario VE (proveedores / nómina) desde `Pago` / `ProcesoNomina`.
     - Validación de referencias bancarias, detección de duplicados y puente con `tesoreria` (eliminando la tabla duplicada en una migración limpia tras migrar la UI `CuentasBancariasEmpresaPage` al endpoint canónico de `finanzas`).
2. **Integration Hub inbound — `facturas_compra` (`in_invoice`):**
   - Extender `OdooXMLRPCClient` y `OdooConnector` para traer `account.move` (`move_type='in_invoice'`) + `get_lineas_factura`.
   - Implementar `_upsert_factura_compra` en `SyncEngine` (espejo de `_upsert_factura_venta` PR `#187`): auto-crea `proveedores.Proveedor` si no existe, persiste `compras.FacturaCompra` + `DetalleFacturaCompra` (*history-only*, idempotente por `(id_empresa, numero_factura)` y `EntidadSincronizada`) y crea/vincula `CuentaPorPagar` sin duplicar.
3. **Integration Hub inbound — Pagos multi-factura y pagos a proveedor (`AsignacionPago`):**
   - Enriquecer `OdooXMLRPCClient.get_pagos` para leer `account.partial.reconcile` (montos conciliados por factura `debit_move_id`/`credit_move_id`, `amount`, `amount_currency`) en lugar de solo `reconciled_invoice_ids`.
   - Actualizar `_upsert_pago` en `SyncEngine` usando **`finanzas.AsignacionPago`** (Bloque A) para:
     - Importar cobros de cliente (`inbound`) reconciliados con **0, 1 o N facturas** (`FacturaFiscal` / `CuentaPorCobrar`), dejando cualquier sobrante como saldo a favor del `core.Contacto`.
     - Importar pagos a proveedor (`outbound`) vinculados a `FacturaCompra` / `CuentaPorPagar` vía `AsignacionPago`.
4. **Cierre de `CTF-011` — Outbound `push` a Odoo validado contra instancia de prueba:**
   - Unificar y completar el `push` bidireccional en `Integration Hub` (complementando la capa opt-in de `bots_ingest/services/odoo_push.py`) para pagos/abonos de cobranza (`cxc` / `cuentas_por_cobrar` → `account.payment` / reconciliación en Odoo) con `Idempotency-Key`, credencial `write_user` de mínimo privilegio, modo borrador/confirmado configurable y pruebas de integración contra el Odoo de prueba.
   - Al verificar en vivo contra Odoo de prueba con CI verde, actualizar [`CTF-011`](../ctf/CTF-011.md) a `CERRADO`.

---

## 3. Secuenciación recomendada de PRs (R-PROC-2)

| Ola | PRs focales sugeridos | Dependencia previa |
|---|---|---|
| **Ola A1** | ✅ `feat(finanzas): modelo AsignacionPago + RLS + backfill Pago.id_contacto` (`PR #297`) | Ninguna |
| **Ola A2** | ✅ `feat(finanzas): servicio atomico conciliacion N:M, anticipos y diferencial cambiario` (`PR #298`) | Ola A1 |
| **Ola A3** | ✅ `feat(finanzas): API REST, MCP y UI ConciliacionContactoDialog en CxC/CxP/Tesoreria` (`PR-12`) | Ola A2 |
| **Ola B1** | ✅ `feat(contabilidad): DiarioContable, contra-asiento, PeriodoContable y cierre ejercicio` (`PR #300`) | Ninguna (paralela a Ola A) |
| **Ola B2** | ✅ `feat(contabilidad): reportes P&L, Balance General, Mayor Auxiliar y Balance Comprobacion PDF/CSV + USD` (`PR-14`) | Ola B1 |
| **Ola B3** | ✅ `feat(compras): flujo transaccional Requisicion->RFQ->Oferta->OC y reglas departamento/SLA en aprobaciones` (`PR-15`) | Ninguna |
| **Ola B4** | `feat(inventario): ReglaReabastecimiento, LoteProducto opt-in y StockUbicacion` | Ninguna |
| **Ola B5** | `refactor(banca): consolida CuentaBancariaEmpresa en finanzas y servicios de pagos masivos` | Ninguna |
| **Ola B6** | `feat(hub): inbound facturas_compra + pagos multi-factura con AsignacionPago` | Ola A2 |
| **Ola B7** | `feat(hub): cierre CTF-011 push outbound cobranza validado contra Odoo de prueba` | Ola A2 + credenciales Odoo prueba |

Cada PR pasa el gate completo de [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md) (`check`, `makemigrations --check --dry-run`, `mapa_superficie --check`, tests con aislamiento multi-tenant + RLS y `diff-cover ≥95%`, `tsc -b`, `npm run lint`, `check:api-drift`, Vitest/Playwright) y recibe dictamen **`APROBADO`** de revisor independiente (`QA + Seguridad`) antes de `ready` y merge a `develop`.
