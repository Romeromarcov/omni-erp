# Changelog — Fase 1 (Ciclo de Negocio Completo)

> Rama: `chore/diagnostico-inicial`  
> Período: 2026-05-14 → 2026-05-16  
> Estado: **EN PROGRESO** — M1–M5 completados, M6–M10 pendientes

---

## Módulos implementados

### M7 — Asientos Contables Automáticos (R-CODE-11)
**Archivos clave:**
- `apps/contabilidad/models.py` — nuevo modelo `MapeoContable`
- `apps/contabilidad/services.py` — nuevo servicio `generar_asiento()`
- `apps/core/models.py` — campo `contabilidad_auto_aprobar` en `Empresa`
- `apps/contabilidad/migrations/0003_add_mapeo_contable.py`

**Regla implementada:** toda operación con impacto contable (factura venta, factura compra, recepción, ajuste, pagos) genera `AsientoContable` dentro del mismo `@transaction.atomic`. Si el asiento falla, la transacción entera revierte.

**Configuración:** `MapeoContable(empresa, tipo_asiento)` → `(cuenta_debe, cuenta_haber)`. Sin mapeo configurado → `AsientoError`.

---

### M2 — Ciclo de Ventas (Pedido → Entrega → Factura)
**Archivos clave:**
- `apps/ventas/services.py` — reescritura completa del ciclo
- `apps/ventas/models.py` — `FacturaFiscal` + campos faltantes
- `apps/ventas/views.py` — fix `reservas_creadas`

**Ciclo correcto implementado:**
1. `confirmar_pedido()` → APROBADO + `reservar_stock()` (sin movimiento físico)
2. `entregar_nota_venta()` → ENTREGADA + `DESPACHO_VENTA` + `liberar_reserva()`
3. `emitir_factura_fiscal()` → EMITIDA + `generar_asiento("FACTURA_VENTA")` (R-CODE-11)

**Fix de revisión de código:** el `save()` de `nota_venta` se movió *después* de `generar_asiento()` para que si el asiento falla, la nota nunca quede en estado FACTURADA.

---

### M3 — Ciclo de Compras (OC → Recepción → Factura)
**Archivos clave:**
- `apps/compras/services.py` — nuevo archivo
- `apps/compras/models.py` — campos `id_empresa`, `monto_total`, `costo_unitario`, `subtotal`, `id_recepcion`
- `apps/compras/migrations/0004_recepcion_detalle_factura_update.py`
- `apps/compras/migrations/0005_facturacompra_id_empresa_not_null.py`

**Servicios implementados:**
- `aprobar_orden_compra()` — transición BORRADOR→APROBADA
- `registrar_recepcion()` — `RECEPCION_COMPRA` + `CuentaPorPagar` + asiento
- `registrar_factura_compra()` — `FacturaCompra` + asiento `FACTURA_COMPRA`

---

### M1 — Contactos Unificados (Strangler Fig)
**Archivos clave:**
- `apps/core/models.py` — nuevo modelo `Contacto`
- `apps/core/serializers.py` — `ContactoSerializer`
- `apps/core/viewsets.py` — `ContactoViewSet`
- `apps/core/urls.py` — registro del router
- `apps/core/mcp_server.py` — herramienta `omni_buscar_contacto`
- `apps/crm/models.py` — FK nullable `contacto` en `Cliente`
- `apps/proveedores/models.py` — FK nullable `contacto` en `Proveedor`
- `apps/rrhh/models.py` — FK nullable `contacto` en `Empleado`
- Migrations: `core.0012`, `crm.0007`, `proveedores.0004`, `rrhh.0002`

**Patrón:** un `Contacto` con flags booleanos (`es_cliente`, `es_proveedor`, `es_empleado`, `es_usuario`). Los modelos legacy mantienen FK nullable para migración gradual.

**Fix de seguridad (revisión de código):** `omni_buscar_contacto` ahora valida que `empresa_id` del parámetro coincide con `empresa_id` del token, evitando acceso cross-tenant.

---

### M4 — Listas de Precios
**Archivos clave:**
- `apps/ventas/models.py` — nuevos modelos `ListaPrecio` y `DetallePrecio`
- `apps/ventas/services.py` — función `obtener_precio()`
- `apps/ventas/migrations/0009_listaprecio_detalleprecio.py`

**Prioridad de resolución de precio:**
1. Lista asignada al contacto (`contacto.lista_precio`)
2. Lista de referencia de la empresa (`es_referencia=True`)
3. `precio_venta_sugerido` del producto (fallback)

**Vigencia:** `vigente_desde` / `vigente_hasta` en `DetallePrecio` — precios vencidos no aplican.

---

### M5 — Control de Salidas Internas de Inventario
**Archivos clave:**
- `apps/inventario/models.py` — nuevos modelos `RequisicionInterna` y `DetalleRequisicion`; `SALIDA_INTERNA` en `MovimientoInventario`
- `apps/inventario/services.py` — `aprobar_requisicion()`, `despachar_requisicion_interna()`, validación cross-tenant
- `apps/inventario/migrations/0005_add_salida_interna_requisicion.py`

**Ciclo:** `RequisicionInterna` BORRADOR → `aprobar_requisicion()` → APROBADA → `despachar_requisicion_interna()` → DESPACHADA + movimientos `SALIDA_INTERNA`.

**Invariante:** ningún `MovimientoInventario` de tipo `SALIDA_INTERNA` puede crearse sin una `RequisicionInterna` APROBADA del mismo tenant. Esto lo valida `registrar_movimiento()` antes de persistir.

**Fix de seguridad (revisión de código):** la búsqueda de `RequisicionInterna` en la validación filtra por `(id_requisicion, id_empresa)` para prevenir que una requisición de empresa A autorice salidas en empresa B.

---

## Resumen de tests

| Módulo | Tests | Estado |
|--------|-------|--------|
| M7 Asientos | 12 | ✅ |
| M2 Ventas | 18 | ✅ |
| M3 Compras | 14 | ✅ |
| M1 Contactos | 14 | ✅ |
| M4 Precios | 8 | ✅ |
| M5 Salidas | 17 | ✅ |
| **Total** | **261** | **✅ 0 fallos** |

---

## Decisiones de arquitectura relevantes

- **`get_or_create` + `select_for_update`** en `reservar_stock()`: el patrón es seguro porque el `select_for_update` re-lee el valor actualizado con el lock activo; no es posible sobre-reservar.
- **Eventos dentro de `@transaction.atomic`** en `confirmar_pedido()`: aceptable dado que Celery usa `TASK_ALWAYS_EAGER=True` en tests y los eventos son best-effort en producción.
- **`lista_precio` FK en `Contacto`** sin constraint cross-tenant: se acepta como limitación conocida; la API filtra por empresa en `get_queryset()`. Una restricción de BD requeriría un trigger o check constraint complejo.

---

## Pendiente (M6–M10)

- **M6** — Flujos Configurables: `ConfiguracionFlujoDocumentos`
- **M8** — Módulo Fiscal Venezuela: IVA, IGTF, retenciones, libros SENIAT
- **M9** — Agentes Operativos: personalization agent (capas 1-2), cobrador estratégico
- **M10** — Infraestructura: reportes PDF, notificaciones email, SaaS core
