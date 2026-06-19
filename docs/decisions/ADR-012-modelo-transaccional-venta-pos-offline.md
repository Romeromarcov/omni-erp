# ADR-012: Modelo Transaccional de Venta POS Offline

**Estado:** Propuesto
**Fecha:** 2026-06-19
**Autor(es):** Marco Romero, Claude Opus 4.8
**Categoría:** Arquitectura — Offline-first (deriva de ADR-001, habilita CTF-008 Nivel 2)

---

## Contexto

ADR-001 estableció offline-first en clientes. CTF-008 Nivel 2 ya entregó la base:

- **Pull de deltas** (`GET /api/sync/pull/`) que refresca la réplica local del
  catálogo (productos, variantes, clientes…) — PR #147/#150/#151.
- **Outbox del cliente** (`salesOutbox`) con reenvío idempotente — PR #156.
- **Idempotencia probada** del alta de ventas por `Idempotency-Key` — PR #149.

Falta cerrar la operación estrella sin red: **vender en el POS**. Aquí aparece
el problema central que este ADR resuelve.

### El problema: la venta POS no es una sola escritura

En el flujo actual (`PosPage`), una venta es una **transacción de varios pasos
en el servidor**, cada uno dependiente del anterior:

1. **Crear la nota** (`POST /ventas/notas-venta/`) → el servidor genera
   `id_nota_venta` **y recalcula IVA y total** (el cliente no es la autoridad
   fiscal).
2. **Registrar los pagos** (`POST /finanzas/pagos/…`) que **referencian el
   `id_nota_venta` que devolvió el servidor**.
3. **Entregar/confirmar** (`.../entregar/`) → despacho de stock, CxC, asiento.

Si se encola en el outbox **solo el paso 1** y se reintenta aislado, se crean
**notas sin pagos ni entrega** (ventas huérfanas) cuando el dispositivo recupera
la red a mitad de camino. Eso es **pérdida/corrupción de datos de dinero**,
justo lo que ADR-001 y el gate de `CLAUDE.md` (R-CODE-4) prohíben.

Además, offline el cliente **no puede** obtener el `id_nota_venta` del servidor
antes de registrar los pagos: el id no existe hasta que la nota se persiste.

---

## Decisión

### 1. La venta offline es UNA unidad atómica con identidad de cliente

El cliente arma la venta completa **en memoria/IndexedDB** y la encola en el
outbox como **un solo sobre** (`VentaOffline`), identificado por un
**`client_uuid` (UUIDv7) generado en el dispositivo**:

```jsonc
{
  "client_uuid": "uuid7-del-dispositivo-para-esta-venta",
  "fecha_local": "2026-06-19T14:03:00-04:00",
  "id_sucursal": "...", "id_caja": "...", "id_cliente": "...",
  "detalles": [{ "id_producto": "...", "cantidad": "2", "precio_unitario": "3.50" }],
  "pagos":    [{ "id_metodo_pago": "...", "id_moneda": "...", "monto": "7.00" }],
  "totales_cliente": { "subtotal": "7.00", "iva": "0.00", "total": "7.00" }
}
```

- El `client_uuid` es la **clave de idempotencia** de toda la venta (no por
  paso). Reenviar el mismo sobre N veces produce **exactamente una** venta.
- Los pagos **no** referencian `id_nota_venta` (no existe aún): se mandan
  **dentro** del sobre y el servidor los liga a la nota que él mismo crea.

### 2. El servidor es la autoridad; los totales del cliente son provisionales

- `totales_cliente` viaja **solo para mostrar un recibo provisional** y para una
  **verificación defensiva** (si difiere del cálculo del servidor más allá de un
  epsilon, el servidor **rechaza** la venta y la marca para revisión — no
  "gana" el cliente en dinero/IVA, R-CODE-4).
- El servidor **recalcula** IVA y total con su lógica fiscal (la misma de hoy) y
  esos son los valores definitivos. El recibo del cliente se reconcilia con la
  respuesta del servidor al sincronizar.

### 3. Endpoint único y atómico

```
POST /api/sync/push/ventas/    (Idempotency-Key: <client_uuid>)
```

- Aplica **nota → pagos → entrega en una sola `@transaction.atomic`**,
  delegando en los **services existentes** (`confirmar_nota_venta`,
  `registrar_efectos_pago`, etc.) — **no se reimplementa lógica de dinero**
  (R-PROC-2).
- **Idempotente** reusando `apps/core/idempotency.py` (scope
  `sync:push-venta`): el primer envío crea la venta y cachea la respuesta
  (incluye el `id_nota_venta` del servidor); los reenvíos devuelven esa misma
  respuesta sin duplicar.
- **Multi-tenant** (R-CODE-1): `id_empresa` se inyecta del usuario, nunca del
  payload.

### 4. Mapeo id local → id servidor

- El cliente indexa la venta en su réplica por `client_uuid`.
- La respuesta del servidor trae `id_nota_venta`; el cliente **guarda el mapeo**
  `client_uuid → id_nota_venta` y reconcilia el recibo/estado local.
- Para imprimir offline se usa un **folio provisional** local marcado como "por
  confirmar"; al sincronizar se muestra el número fiscal real del servidor.

### 5. Orden, reintentos y fallos

- El outbox envía las ventas **en orden FIFO** y de a una; no avanza a la
  siguiente hasta confirmar la actual (evita carreras de stock/secuencia).
- **2xx** → venta confirmada, se concilia y se saca del outbox.
- **4xx de validación** (p.ej. totales incoherentes, producto inexistente) →
  la venta se mueve a un estado **"requiere revisión"** visible para el cajero;
  **no** se reintaza en bucle (no es transitorio).
- **5xx / red** → reintento con backoff (el `client_uuid` garantiza no
  duplicar).

### 6. Stock e inventario

- Offline, el stock mostrado es el del **último pull** (puede estar desfasado).
- El servidor aplica el despacho real al confirmar; si el stock no alcanza,
  la política (rechazar vs. permitir negativo con alerta) se define por
  configuración de tenant y **queda fuera de este ADR** (se decide al
  implementar el endpoint). Este ADR solo fija que **la verdad de stock es del
  servidor al confirmar**, no del cliente.

---

## Alcance y límites

**Cubre:** ventas POS de contado/credito creadas offline (nota + pagos +
entrega) como unidad atómica idempotente.

**No cubre (PRs/decisiones posteriores):**
- Devoluciones offline.
- Política de stock insuficiente al confirmar (config de tenant).
- Edición offline de documentos existentes (eso es el *version-check* de
  updates, decisión aparte).

---

## Consecuencias

**Positivas**
- Sin ventas huérfanas: la venta es todo-o-nada.
- Reutiliza la lógica fiscal/contable existente (cero divergencia, R-PROC-2).
- Idempotencia ya construida y probada; el cliente nunca duplica dinero.
- El servidor sigue siendo la autoridad fiscal (R-CODE-4).

**Negativas / costos**
- El recibo offline es **provisional** hasta sincronizar (el número fiscal real
  lo asigna el servidor). Es aceptable y honesto con el cajero.
- Requiere un endpoint nuevo que orqueste nota+pagos+entrega — trabajo de dinero
  que **exige tests exhaustivos** (happy path, reenvío, totales incoherentes,
  fallo a mitad → rollback completo, aislamiento multi-tenant) antes de mergear.

---

## Plan de implementación (PRs focales posteriores)

1. **Backend**: `POST /api/sync/push/ventas/` atómico + idempotente, con la
   batería de tests anterior. (PR de dinero — revisión cuidadosa.)
2. **Frontend**: `PosPage` arma el sobre `VentaOffline`, lo encola en
   `salesOutbox` al detectar fallo de red, y un flujo de **flush al volver
   online** que reconcilia `client_uuid → id_nota_venta`.
3. **Frontend**: UI de estado de cola (ventas "por confirmar" / "requiere
   revisión") para el cajero.

---

## Referencias

- ADR-001 — PostgreSQL en servidor + offline-first en clientes.
- CTF-008 — Resiliencia offline (Nivel 2).
- `apps/core/idempotency.py` — infraestructura de idempotencia reusada.
- PRs #147, #149, #150, #151, #156 — base de sync (pull, idempotencia, outbox).
