# Integration Hub — Estado y avances

> Última actualización: 2026-06-22. Documenta el estado del Integration Hub tras
> el trabajo de conexión Odoo + visión "Omni como hub" (Fases 1–2 inbound y
> Fase 3 completadas).

## 1. Visión

El Integration Hub funciona como **puente/traductor entre sistemas** (estilo
Make/Zapier), con una regla central: **la data siempre pasa por Omni y se
almacena en Omni con su estructura canónica**. Así, aunque un cliente use Omni
solo como puente (p. ej. Odoo → Google Sheets), su histórico se va acumulando en
Omni para una futura migración de procesos.

Caso de referencia: **Lubrikca** (puente Odoo ↔ Google Sheets).

## 2. Arquitectura (resumen)

- `ConectorProveedor`: catálogo de tipos de integración (odoo, google_sheets…).
  La **lógica** de cada conector es una clase Python registrada en `apps.py`
  (no se crea un conector funcional solo con una fila del catálogo).
- `ConectorInstancia`: una conexión configurada por empresa (multi-tenant).
- `EntidadSincronizada`: mapa `id_externo ↔ id_omni` + checksum (dedup), por
  instancia y tipo de entidad. **No** guarda datos de negocio.
- **Inbound** (`SyncEngine`): trae datos del sistema externo y los **persiste en
  los modelos canónicos de Omni** vía `_upsert_en_omni` (handler por entidad).
- **Outbound/export** (`ExportEngine`): lee de un conector origen y escribe en
  un destino; además **persiste en Omni** (`SyncEngine.ingerir_en_omni`) — el
  dato fluye Odoo → **Omni** → Sheets, no Odoo → Sheets directo.

### Convenciones de los handlers de persistencia (Fase 2)
- **Idempotencia** por clave natural por empresa (p. ej. `numero_pedido`,
  `numero_orden`) y por `referencia_externa` (= id externo de Odoo) en maestros.
- **Auto-creación de maestros** (decisión del owner, 2026-06-19): si el
  Cliente/Proveedor no existe, se crea; se enlaza al `core.Contacto` ya
  sincronizado y se reutiliza su RIF si está disponible.
- **Líneas**: los productos se resuelven por el mapa `EntidadSincronizada`; las
  líneas cuyo producto aún no está sincronizado **se omiten** (no rompen el
  documento).
- Multi-tenant siempre (R-CODE-1); dinero/cantidades en `Decimal` (R-CODE-4);
  sin secretos en logs (R-CODE-8).

## 3. Estado por componente

### En producción (`main`)
- **Fix conexión Odoo**: `normalize_odoo_host()` reduce el host a
  `esquema://dominio` (tolera pegar la URL de login `/web/login`, que causaba
  `ResponseNotReady`). Edición de conectores desde la UI (botón Editar + modal;
  la `api_key` se conserva si se deja en blanco). Campo "Base de datos" opcional
  para Odoo. Fix de vulnerabilidad `undici`. (PR #145)
- **Integration Hub Fase 1**: la exportación a Google Sheets persiste la data en
  Omni (`ExportEngine` → `ingerir_en_omni`), con flag `persistir_en_omni`. (PR #148)

### En `develop` (staging) — además de lo de producción
- **Fase 2 — persistencia inbound por entidad**:
  - `pedidos_venta` → `ventas.Pedido` + `DetallePedido`, auto-crea `crm.Cliente`. (PR #159)
  - `pedidos_compra` → `compras.OrdenCompra` + `DetalleOrdenCompra`, auto-crea
    `proveedores.Proveedor`. (PR #164)
  - `inventario` → `inventario.StockActual` (almacén por defecto `IH-IMPORT`). (PR #166)

Hoy, al sincronizar Odoo, Omni almacena: **contactos, productos, pedidos de
venta, órdenes de compra e inventario** (contactos/productos venían de Fase 1).

### Panel de administración (ya existente)
- El **Panel SaaS** para gestionar proveedores de integración existe en
  `/admin-saas/proveedores` (lista + formulario), gateado por
  `es_superusuario_omni`. Solo aparece en el menú si la cuenta tiene ese flag.

## 4. Estado de Fase 2 (inbound) y Fase 3 — COMPLETADAS (2026-06-22)

Cerradas por el loop autónomo (todas con tests y revisión independiente):

- **✅ `facturas_venta`** (PR #187): el conector trae `account.move.line`
  (`client.get_lineas_factura`) y `_upsert_factura_venta` persiste
  `ventas.FacturaFiscal` + `DetalleFacturaFiscal`. Documento fiscal **importado**
  (estado `EMITIDA`/`PAGADA`): refleja una factura ya emitida en el externo para
  acumular histórico; no re-emite ni dispara numeración (`numero_control` = número
  externo). Idempotente por `(empresa, numero_factura)`.
- **✅ `pagos`** (PR #188): `client.get_pagos` trae `reconciled_invoice_ids` y
  `_upsert_pago` persiste `finanzas.Pago` **history-only** (sin side-effects: no
  crea `TransaccionFinanciera` ni mueve saldos). **Límite actual:** solo cobros de
  cliente (`inbound`/`customer`) reconciliados con **exactamente una** factura ya
  sincronizada; multi-factura/parcial y pagos a proveedor (→ CxP) quedan como
  trabajo posterior (requieren montos de conciliación por documento).
- **✅ Fase 3 — registry dinámico** (PR #189): `ConectorProveedor.clase_conector`
  (ruta dotted) se carga vía `import_string` sin re-desplegar; el catálogo no es
  editable por tenants (campo no serializado, escritura superusuario).
- **✅ Fase 3 — conector genérico REST** (PR #190): `GenericRestConnector`
  config-driven (`base_url`/`headers`/`entidades` con mapa de campos), se conecta
  vía el registry dinámico. **Límite actual:** `pull` de `contactos` y `productos`
  (las demás entidades se añaden ampliando el mapa). CSV y `push` quedan pendientes.

## 4.1 Pendiente (siguiente)

- **`pagos` — reconciliación parcial/múltiple** y **pagos a proveedor → CxP**.
- **Conector genérico** — más entidades (pedidos/facturas/inventario), origen CSV
  y soporte `push` (outbound).

## 5. Notas técnicas / aprendizajes

- **CI corre `pytest tests/`, no `apps/`**: los tests in-app de
  `apps/**/tests/` no cuentan para cobertura en CI. Los tests nuevos deben vivir
  bajo `tests/` para que el gate **`diff-cover`** (≥95% en líneas nuevas vs
  `main`) los considere.
- **`diff-cover` compara contra `origin/main`**: al verificar localmente, hacer
  `git fetch origin main` primero.
- **Cadena de PRs sobre `sync_engine.py`**: como todos los handlers viven en el
  mismo archivo, las rebanadas de Fase 2 van **secuenciales** (cada una parte de
  que la anterior ya esté en `develop`); si se encadenan, al mergear con squash
  se recrean limpio desde `develop` (cherry-pick del commit de la rebanada).

## 6. Limitaciones conocidas

- **Resolución de producto en líneas**: usa el id de `product.template` mapeado;
  variantes (`product.product`) con id distinto quedan sin resolver y la línea se
  omite. A afinar en una rebanada posterior.
- **Auto-creación de maestros**: crea `Cliente`/`Proveedor` con el RIF del
  contacto sincronizado si existe, o vacío; el `create` por ORM no dispara el
  validador de RIF (idempotencia por `referencia_externa`).
