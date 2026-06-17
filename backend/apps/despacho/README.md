# App `despacho`

Despacho/entrega de mercancía (sub-fase **1.G** del Plan Maestro): documenta la
**logística de entrega** de una venta — quién la transporta, a dónde, cuándo salió,
cuándo se entregó (con receptor/firma) o si volvió.

**Prefijo API:** `/api/despacho/`

## Decisiones de diseño (1.G, backend)

1. **No toca inventario.** El stock físico ya salió con el movimiento
   `DESPACHO_VENTA` que registra `apps.ventas.services.entregar_nota_venta()` al
   confirmar la venta. Crear, entregar, devolver o cancelar un `Despacho` **nunca**
   crea `MovimientoInventario`. El reingreso de mercancía es un flujo aparte
   (`DevolucionVenta`, apps/ventas).
2. **Origen = NotaVenta confirmada.** Solo se despacha desde notas `ENTREGADA` o
   `FACTURADA` (estados posteriores a la salida de stock). `id_pedido` queda como
   referencia informativa del documento raíz. Se eliminó `id_orden_compra` (la
   entrada de compras la cubre `RecepcionMercancia`; un despacho es saliente).
3. **Despacho parcial por líneas.** `DetalleDespacho` (la "LineaDespacho" del plan;
   nombre consistente con `DetallePedido`/`DetalleNotaVenta`) permite repartir una
   venta en varios viajes. Regla: por producto, la suma despachada en despachos
   `PENDIENTE`/`EN_RUTA`/`ENTREGADO` de la nota **no puede exceder lo vendido**
   (sobre-despacho → 400). `CANCELADO` y `DEVUELTO` liberan cupo.
4. **Máquina de estados con timestamp por transición:**

   ```
   PENDIENTE ──iniciar-ruta──▶ EN_RUTA ──entregar──▶ ENTREGADO   (fecha_entrega_real)
       │                          └──devolver──▶ DEVUELTO        (fecha_devolucion)
       └──cancelar──▶ CANCELADO                                  (fecha_cancelacion)
   ```

   `ENTREGADO`/`DEVUELTO`/`CANCELADO` son terminales. Lo que ya salió en ruta no se
   cancela: se devuelve. Receptor, documento y firma de la entrega quedan en
   `documento_json["entrega"]`; los motivos en `documento_json["devolucion"|"cancelacion"]`.
5. **Numeración:** correlativo fiscal por empresa (`fiscal.NumeroCorrelativo`,
   tipo `DESPACHO`); `numero_despacho` es único por empresa (multi-tenant).
6. **Sin DELETE:** los despachos no se borran (HTTP 405) — el ciclo se cierra con
   `CANCELADO`/`DEVUELTO` para no perder trazabilidad. Las líneas son de solo
   lectura por API (editar líneas sueltas burlaría la validación de cupo).
7. **RLS (lote 3):** `despacho_despacho` tiene Row Level Security forzada en
   PostgreSQL (registro en `apps/core/rls.py` + migración `0004_rls_lote3_despacho`).
   `despacho_detalle_despacho` no tiene columna de empresa (pertenece vía
   `id_despacho`), como el resto de tablas "detalle" del rollout.

## Modelos

| Modelo | Descripción |
|---|---|
| `Despacho` | Encabezado (TenantModel + IntegrationFieldsMixin): venta origen, almacén, dirección de entrega, transportista, estado, timestamps por transición. |
| `DetalleDespacho` | Línea de despacho (producto/cantidad/unidad/lote). |

## Endpoints

| Método/Ruta | Descripción |
|---|---|
| `GET/POST /despachos/` | CRUD del encabezado (estado y número read-only). Filtros: `?estado=`, `?id_transportista=`, `?id_nota_venta=`, `?fecha_desde=`, `?fecha_hasta=`, `?search=`. |
| `POST /despachos/desde-nota-venta/` | Crea despacho desde una venta confirmada (total o parcial por `lineas`). |
| `POST /despachos/{pk}/iniciar-ruta/` | `PENDIENTE → EN_RUTA` (opcional `id_transportista`). |
| `POST /despachos/{pk}/entregar/` | `EN_RUTA → ENTREGADO` (`receptor` obligatorio, `firma_base64` opcional). |
| `POST /despachos/{pk}/devolver/` | `EN_RUTA → DEVUELTO` (`motivo` obligatorio). |
| `POST /despachos/{pk}/cancelar/` | `PENDIENTE → CANCELADO` (`motivo` obligatorio). |
| `GET /despachos/{pk}/pdf/` | Nota de entrega en PDF. |
| `GET /detalles-despacho/` | Líneas (solo lectura; filtro `?id_despacho=`). |

## MCP

`despacho_get_pendientes` (scope `despacho:read`): lista despachos
`PENDIENTE`/`EN_RUTA` de la empresa del token — para que los agentes consulten qué
falta por entregar. Las transiciones quedan para operadores humanos vía API.
