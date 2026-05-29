# Plan de Trabajo Detallado — Fase 1: MVP AI-Nativo Vendible

**Versión:** 1.0  
**Fecha:** 2026-05-16  
**Duración estimada:** 12-16 semanas  
**Criterio de éxito:** Un cliente venezolano pagando una suscripción y operando en producción.

---

## Estado de arranque

La auditoría de código al cierre de Fase 0 reveló los siguientes gaps críticos que este plan resuelve:

| Gap | Módulo afectado | Severidad |
|-----|-----------------|-----------|
| Contacto/Cliente/Proveedor son modelos separados, sin unificación | crm, proveedores, rrhh | Alta |
| `confirmar_pedido()` genera DESPACHO_VENTA en el momento incorrecto | ventas | Alta |
| Compras tiene modelos pero sin servicios (ciclo muerto) | compras | Alta |
| Ningún módulo genera asientos contables automáticamente | contabilidad | Alta |
| No existen listas de precios | finanzas/ventas | Media |
| Salida de inventario no está controlada por origen | inventario | Media |
| No hay flujos configurables por empresa | core | Media |
| Fiscal Venezuela ausente (IVA, IGTF, retenciones, SENIAT) | fiscal | Alta |

---

## Módulos de Trabajo

### M1 — Contactos Unificados

**Objetivo:** Un solo registro `Contacto` que puede ser cliente, proveedor, empleado, usuario, o todos a la vez. Patrón Odoo.

**Regla clave:** R-CODE-11 no aplica aquí. R-CODE-1 sí (id_empresa en Contacto).

**Tareas:**

- [ ] **M1-T1:** Crear modelo `Contacto` en `apps/core/models.py`
  - Campos: `id_contacto` (UUIDv7), `id_empresa`, `tipo_persona` (NATURAL/JURIDICA), `nombre`, `apellido`, `razon_social`, `rif`, `cedula`, `email`, `telefono`, `direccion_fiscal`
  - Roles booleanos: `es_cliente`, `es_proveedor`, `es_empleado`, `es_usuario`
  - Campos de cliente: `tipo_credito` (CONTADO/CREDITO), `limite_credito`, `dias_credito`, `lista_precio` (FK)
  - Campos de proveedor: `cuenta_bancaria`, `dias_pago`
  - FK a `User` de Django (nullable, para el rol usuario)
  - `activo=True` (soft delete)

- [ ] **M1-T2:** Migración strangler fig — `Cliente` y `Proveedor` adquieren FK `contacto` (nullable inicialmente)
  - Datos: script de migración que crea un `Contacto` por cada `Cliente` y `Proveedor` existente y enlaza la FK.
  - Los modelos legados quedan como wrappers durante la transición.

- [ ] **M1-T3:** Enlazar `Empleado` a `Contacto` (FK nullable; en Fase 2 se hace obligatoria)

- [ ] **M1-T4:** ViewSet `ContactoViewSet` con filtros por rol (`?es_cliente=true`, `?es_proveedor=true`)

- [ ] **M1-T5:** MCP tool `omni_buscar_contacto(query, empresa_id, rol=None)` — reemplaza las búsquedas separadas de cliente/proveedor

- [ ] **M1-T6:** Tests: aislamiento multi-tenant, creación de contacto con múltiples roles, búsqueda por RIF

**DoD M1:** Un solo `Contacto` puede ser cliente y proveedor simultáneamente. Datos migrados sin pérdida. ViewSet y MCP tool funcionando.

---

### M2 — Ciclo de Ventas Correcto

**Objetivo:** Corregir el flujo ventas para que stock se comprometa en Pedido pero solo salga en entrega. CxC generada automáticamente en entrega.

**Regla clave:** R-CODE-11 aplica en FacturaFiscal.

**Tareas:**

- [ ] **M2-T1:** Corregir `ventas/services.py → confirmar_pedido()`
  - Eliminar la creación de `MovimientoInventario(tipo=DESPACHO_VENTA)` — eso es incorrecto aquí.
  - En su lugar: incrementar `ProductoInventario.cantidad_comprometida` para cada línea del pedido.
  - Mantener la creación de `CuentaCobrar` solo si `contacto.tipo_credito == 'CREDITO'` (usar nuevo modelo `Contacto`).

- [ ] **M2-T2:** Implementar `entregar_pedido(nota_venta_id)` en `ventas/services.py`
  - Precondición: `NotaVenta.estado == 'BORRADOR'` y `Pedido.estado == 'APROBADO'`
  - Para cada línea: crea `MovimientoInventario(tipo='DESPACHO_VENTA', cantidad=...)` — esto descuenta stock físico y libera `cantidad_comprometida`.
  - Genera `CuentaCobrar` si el pedido no la generó aún (ventas al contado sin pedido previo).
  - Cambia `NotaVenta.estado = 'ENTREGADA'`.
  - Todo en `@transaction.atomic`.

- [ ] **M2-T3:** Implementar `emitir_factura_fiscal(nota_venta_id)` en `ventas/services.py`
  - Crea `FacturaFiscal` desde la `NotaVenta`.
  - Asigna número correlativo (ver M8).
  - Llama a `contabilidad_services.generar_asiento('FACTURA_VENTA', factura, empresa)` — R-CODE-11.
  - Cambia `NotaVenta.estado = 'FACTURADA'`.
  - Todo en `@transaction.atomic`.

- [ ] **M2-T4:** Agregar `ConfiguracionFlujoVentas` (ver M6) para que cada empresa decida qué pasos son obligatorios.

- [ ] **M2-T5:** Tests end-to-end:
  - `test_ciclo_ventas_completo`: cotización → pedido (verifica `cantidad_comprometida` sube, no stock físico) → entrega (verifica stock baja, CxC creada) → factura (verifica asiento creado).
  - `test_pedido_no_mueve_stock_fisico`.
  - `test_entrega_sin_pedido_aprobado_falla`.

**DoD M2:** Tests end-to-end pasan. `confirmar_pedido()` no genera movimiento de inventario. `entregar_pedido()` sí lo genera. Asiento creado en emisión de factura.

---

### M3 — Ciclo de Compras Completo

**Objetivo:** El módulo compras tiene modelos pero ningún servicio. Implementar el ciclo completo con asientos automáticos.

**Regla clave:** R-CODE-11 aplica en FacturaCompra y RecepcionMercancia.

**Tareas:**

- [ ] **M3-T1:** Implementar `compras/services.py → aprobar_orden_compra(orden_compra_id)`
  - Valida que OC esté en PENDIENTE.
  - Cambia estado a APROBADA.
  - Emite notificación al proveedor (placeholder en Fase 1, real en M10).

- [ ] **M3-T2:** Implementar `registrar_recepcion(orden_compra_id, items_recibidos)`
  - Crea `RecepcionMercancia`.
  - Para cada ítem: crea `MovimientoInventario(tipo='ENTRADA_COMPRA', ...)` — incrementa stock físico.
  - Genera `CuentaPagar` automáticamente (espejo de CxC).
  - Llama a `contabilidad_services.generar_asiento('RECEPCION_MERCANCIA', recepcion, empresa)` — R-CODE-11.
  - Todo en `@transaction.atomic`.

- [ ] **M3-T3:** Implementar `registrar_factura_compra(recepcion_id, datos_factura)`
  - Crea `FacturaCompra` enlazada a `RecepcionMercancia`.
  - Llama a `contabilidad_services.generar_asiento('FACTURA_COMPRA', factura, empresa)` — R-CODE-11.
  - Todo en `@transaction.atomic`.

- [ ] **M3-T4:** ViewSets para `OrdenCompra`, `RecepcionMercancia`, `FacturaCompra` con acciones custom (`aprobar`, `recepcionar`, `facturar`).

- [ ] **M3-T5:** Tests end-to-end:
  - `test_ciclo_compras_completo`: OC → recepción (verifica stock sube, CxP creada, asiento) → factura compra (verifica asiento).
  - `test_recepcion_parcial`: OC de 100 unidades, recepción de 60.

**DoD M3:** Ciclo completo funcionando. Stock aumenta en recepción. Dos asientos generados (recepción + factura). CxP creada.

---

### M4 — Listas de Precios

**Objetivo:** Soporte para múltiples listas de precios por empresa. Lista 1 = precio de referencia, siempre visible en documentos CxC.

**Regla clave:** R-CODE-4 (Decimal). R-CODE-11 no aplica.

**Tareas:**

- [ ] **M4-T1:** Crear modelos en `apps/finanzas/models.py` (o `apps/ventas/`):
  - `ListaPrecio`: `id_lista`, `id_empresa`, `nombre`, `codigo` (ej: "LISTA1", "LISTA2"), `es_referencia` (bool), `moneda` (FK), `activo`.
  - `DetallePrecio`: `id_detalle`, `lista` (FK), `producto` (FK), `precio` (Decimal 18,4), `precio_minimo` (Decimal 18,4), `vigente_desde`, `vigente_hasta` (nullable).

- [ ] **M4-T2:** Lógica de resolución de precio en `ventas/services.py → obtener_precio(producto, contacto, empresa, fecha=None)`:
  - Usar lista asignada al `Contacto`, si no, usar Lista 1 de la empresa.
  - Respetar `vigente_desde` / `vigente_hasta`.

- [ ] **M4-T3:** En todos los documentos CxC (FacturaFiscal, estado de cuenta), mostrar también el precio de Lista 1 si el precio aplicado es distinto.

- [ ] **M4-T4:** ViewSet `ListaPrecioViewSet` con acción `importar_masivo` (CSV con producto + precio).

- [ ] **M4-T5:** Tests: resolución de precio por lista asignada al cliente, fallback a Lista 1, precio fuera de vigencia.

**DoD M4:** Múltiples listas configurables. Precio resuelto automáticamente en cotización/pedido. Lista 1 visible en documentos.

---

### M5 — Control de Salidas de Inventario

**Objetivo:** Garantizar que el stock solo salga por vías válidas y documentadas.

**Regla clave:** R-CODE-11 aplica en AjusteInventario con impacto contable.

**Tareas:**

- [ ] **M5-T1:** Crear modelo `RequisicionInterna` en `apps/inventario/models.py`:
  - Campos: `id_requisicion`, `id_empresa`, `solicitante` (FK Contacto/Empleado), `destino` (EMPLEADO/MUESTRA/OBSEQUIO/CONSUMO_INTERNO), `estado` (BORRADOR→APROBADA→DESPACHADA→ANULADA).
  - Líneas: `DetalleRequisicionInterna` con producto, cantidad solicitada, cantidad despachada.
  - Separado de `RequisicionCompra` (que es para compras externas).

- [ ] **M5-T2:** Implementar `despachar_requisicion_interna(requisicion_id)`:
  - Crea `MovimientoInventario(tipo='SALIDA_INTERNA', ...)`.
  - Si el destino tiene costo (MUESTRA, OBSEQUIO), llama a `generar_asiento('SALIDA_INTERNA', ...)` — R-CODE-11.

- [ ] **M5-T3:** Validación en `MovimientoInventario` — en el servicio `crear_movimiento()`, rechazar tipo SALIDA sin documento origen de tipo válido:
  - `DESPACHO_VENTA` → requiere `NotaVenta` en estado ENTREGADA.
  - `AJUSTE_INVENTARIO` → requiere `AjusteInventario` aprobado.
  - `SALIDA_INTERNA` → requiere `RequisicionInterna` aprobada.
  - Cualquier intento de salida directa sin documento origen lanza `ValueError`.

- [ ] **M5-T4:** `AjusteInventario` aprobado → `generar_asiento('AJUSTE_INVENTARIO', ...)` — R-CODE-11.

- [ ] **M5-T5:** Tests: intento de salida directa sin origen falla. Ajuste negativo genera asiento de pérdida. Requisición interna despachada genera movimiento.

**DoD M5:** Ninguna salida de inventario sin documento origen válido. `RequisicionInterna` funcional. Ajustes generan asientos.

---

### M6 — Flujos Configurables por Empresa

**Objetivo:** Cada empresa puede decidir qué pasos del ciclo de ventas/compras son obligatorios o se pueden saltar.

**Tareas:**

- [ ] **M6-T1:** Crear modelo `ConfiguracionFlujoDocumentos` en `apps/core/models.py`:
  - `id_empresa`, `tipo_documento` (VENTAS/COMPRAS), `paso` (COTIZACION/PEDIDO/NOTA_ENTREGA/FACTURA), `obligatorio` (bool), `orden`.
  - Default: todos los pasos obligatorios.

- [ ] **M6-T2:** Cargar configuración en servicios de ventas/compras:
  - `confirmar_pedido()` verifica si COTIZACION era obligatoria y si existe.
  - `entregar_pedido()` verifica si PEDIDO era obligatorio y si existe.
  - Si el paso es opcional y no existe, el servicio lo crea con estado dummy.

- [ ] **M6-T3:** API endpoint para gestionar `ConfiguracionFlujoDocumentos` (solo admin de empresa).

- [ ] **M6-T4:** Tests: empresa con cotización obligatoria falla si no existe; empresa con cotización opcional puede ir directo a pedido.

**DoD M6:** Al menos cotización (en ventas) y solicitud de cotización (en compras) son configurables como opcionales.

---

### M7 — Servicio de Asientos Contables Automáticos

**Objetivo:** Implementar `contabilidad/services.py` con la función central `generar_asiento()` y los mapeos para todos los tipos de transacción.

**Regla clave:** Este módulo es la implementación de R-CODE-11.

**Tareas:**

- [ ] **M7-T1:** Crear `apps/contabilidad/services.py`:
  ```python
  @transaction.atomic
  def generar_asiento(tipo: str, documento, empresa) -> AsientoContable
  ```
  - Tipos soportados en Fase 1: `FACTURA_VENTA`, `FACTURA_COMPRA`, `RECEPCION_MERCANCIA`, `AJUSTE_INVENTARIO`, `SALIDA_INTERNA`, `PAGO_CXC`, `PAGO_CXP`.

- [ ] **M7-T2:** Crear modelo `MapeoContable` o usar configuración fija:
  - Por `(tipo_asiento, id_empresa)`: qué cuenta va al debe y qué cuenta va al haber.
  - Default Venezuela: cuentas estándar del plan de cuentas SENIAT.
  - Configurable por empresa para adaptación.

- [ ] **M7-T3:** Agregar campo `contabilidad_auto_aprobar` (bool, default False) a `Empresa`.

- [ ] **M7-T4:** Tests unitarios de `generar_asiento()` para cada tipo — sin DB si se usa fixture; verificar que si falla el asiento, la transacción externa se revierte.

- [ ] **M7-T5:** Test de integración que llama a cada servicio de origen (ventas, compras, inventario) y verifica que el asiento queda creado.

**DoD M7:** `generar_asiento()` implementado para los 7 tipos. Tests pasan. Rollback verificado.

---

### M8 — Módulo Fiscal Venezuela

**Objetivo:** Cumplimiento fiscal completo: IVA, IGTF, retenciones, numeración correlativa, libros SENIAT, PDF.

**Tareas:**

- [ ] **M8-T1:** Crear `apps/fiscal_vzla/` con modelos:
  - `ConfiguracionFiscal`: `tasa_iva` (Decimal), `tasa_igtf` (Decimal), `aplica_retencion_iva` (bool), `porcentaje_retencion_iva` (75 o 100), `aplica_retencion_islr` (bool), `numero_control_actual` (int), `numero_factura_actual` (int).
  - `NumeroCorrelativo`: secuencia por empresa y tipo (FACTURA, NOTA_DEBITO, NOTA_CREDITO).

- [ ] **M8-T2:** Lógica de cálculo de impuestos en `fiscal_vzla/services.py → calcular_impuestos(subtotal, contacto, empresa)`:
  - IVA al 12%.
  - IGTF al 3% si pago en divisas.
  - Retención IVA si el cliente es agente de retención.
  - Retención ISLR según tabla de honorarios/compras.

- [ ] **M8-T3:** Numeración correlativa en `emitir_factura_fiscal()`:
  - `select_for_update()` en `ConfiguracionFiscal` para garantizar unicidad.
  - Asigna número de control y número de factura.

- [ ] **M8-T4:** Generación de PDF de factura fiscal con WeasyPrint o ReportLab:
  - Campos obligatorios SENIAT: RIF emisor, RIF receptor, número de control, número de factura, fecha, base imponible, IVA, total.
  - Template HTML + CSS → PDF.

- [ ] **M8-T5:** Libros de compras y ventas SENIAT:
  - Endpoint que genera el TXT en formato SENIAT para un período.
  - Endpoint que genera PDF del libro.

- [ ] **M8-T6:** Tests: cálculo de IVA correcto, IGTF solo en divisas, número correlativo sin duplicados bajo concurrencia (test con threading).

**DoD M8:** Factura fiscal con número correlativo único, IVA e IGTF calculados, PDF descargable. Libros SENIAT generables.

---

### M9 — Agentes Operativos Fase 1

**Objetivo:** Cuatro agentes en modo "sugerir" (shadow mode extendido), más el agente de personalización.

**Tareas:**

- [ ] **M9-T1:** Agente de personalización Capa 1 (preferencias de UI/idioma/formato):
  - Conversación → modifica `PersonalizacionConfig` primitiva `campos`.
  - Usa DSL de ADR-005.

- [ ] **M9-T2:** Agente de personalización Capa 2 (configuración de negocio):
  - Conversa para modificar `ConfiguracionFlujoDocumentos`, listas de precios, límites de crédito.
  - Genera un plan de cambios, lo muestra al usuario, aplica con confirmación.

- [ ] **M9-T3:** Agente estratega de cobranza:
  - Input: facturas vencidas de la empresa.
  - Output: sugerencia de contacto (quién llamar hoy), monto a exigir, mensaje de WhatsApp (template).
  - Shadow mode: `PrediccionAgente(agente='COBRANZA', ...)`.

- [ ] **M9-T4:** Agente sugeridor de reorden:
  - Input: stock actual + histórico de ventas (últimos 30 días).
  - Output: lista de productos a reordenar con cantidad sugerida y proveedor preferido.
  - Shadow mode: `PrediccionAgente(agente='REORDEN', ...)`.

- [ ] **M9-T5:** Eval suites para agentes M9-T3 y M9-T4 (mínimo 30 casos dorados cada uno, precisión objetivo ≥ 75%).

**DoD M9:** 5 agentes en modo sugerir. Eval suites pasando. Métricas visibles en dashboard de agentes.

---

### M10 — Infraestructura de Soporte

**Objetivo:** Reportes, notificaciones y SaaS core mínimo.

**Tareas:**

- [ ] **M10-T1:** PDF de factura fiscal (compartido con M8-T4).

- [ ] **M10-T2:** PDF de cotización, nota de entrega, estado de cuenta CxC.

- [ ] **M10-T3:** Email de factura (HTML + PDF adjunto) via SendGrid o SMTP configurado por empresa.

- [ ] **M10-T4:** In-app notifications: `Notificacion` model, endpoint SSE o polling para frontend.

- [ ] **M10-T5:** `SaasCore` mínimo: `Plan` (FREE/BASIC/PRO), `Suscripcion` (fecha inicio, fecha vencimiento, estado), middleware que verifica suscripción activa en cada request.

- [ ] **M10-T6:** `vzla-localization-pack` como Django app instalable: incluye `fiscal_vzla`, templates de factura, configuraciones default del plan de cuentas Venezuela.

**DoD M10:** PDFs generables para los 4 tipos de documento. Email de factura enviable. Suscripción verificada en requests.

---

## Secuencia de Implementación Recomendada

```
Semanas 1-2:   M7 (servicio asientos) + M1 (contactos — modelo + migración)
Semanas 3-4:   M2 (ventas correcto) + M3 (compras servicios)
Semanas 5-6:   M4 (listas de precios) + M5 (control inventario)
Semanas 7-8:   M8 (fiscal Venezuela — cálculos + numeración)
Semanas 9-10:  M6 (flujos configurables) + M8 (PDF + libros SENIAT)
Semanas 11-12: M9 (agentes) + M10 (reportes + notificaciones)
Semanas 13-14: M10 (SaaS core) + vzla-localization-pack
Semanas 15-16: Buffer: cliente design partner, incidentes, ajustes
```

**Dependencias críticas:**
- M7 debe estar antes de M2, M3, M5 (todos necesitan `generar_asiento()`).
- M1 debe estar antes de M2, M3, M4 (usan `Contacto`).
- M8 (cálculos fiscales) debe estar antes de M8 (PDF) — secuencial interno.
- M9 puede empezar en paralelo con M6 desde semana 9.

---

## Checklist de Apertura de Cada PR en Fase 1

Además del auto-checklist base (sección 6.3 del plan maestro), cada PR de Fase 1 debe responder:

- [ ] ¿Este módulo tiene impacto contable? Si sí, ¿llama a `generar_asiento()` dentro de `@transaction.atomic`? (R-CODE-11)
- [ ] ¿Este módulo usa `Cliente` o `Proveedor` directamente? Si sí, ¿tiene plan de migración a `Contacto`?
- [ ] ¿Alguna salida de inventario ocurre sin documento origen? Si sí, es un bug.
- [ ] ¿El test end-to-end del módulo verifica que el asiento contable existe después de la operación?
