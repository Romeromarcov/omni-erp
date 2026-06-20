# Integration Hub — Estado y avances

> Última actualización: 2026-06-19. Documenta el estado del Integration Hub tras
> el trabajo de conexión Odoo + visión "Omni como hub" (Fases 1–2).

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

## 4. Pendiente

- **`facturas_venta`**: persistir `ventas.FacturaFiscal` + líneas. Requiere
  **enriquecer el conector** Odoo para traer `account.move.line` (el conector hoy
  no trae líneas de factura).
- **`pagos`**: persistir `finanzas.Pago`. Requiere enriquecer el conector con la
  **reconciliación** `account.payment` ↔ documentos.
- **Fase 3**: registry **dinámico** de conectores (cargar la clase desde
  `ConectorProveedor` sin desplegar) + **conector genérico** (REST/CSV) para
  sumar sistemas sin escribir código por cada uno. Independiente de
  `sync_engine.py`.

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
