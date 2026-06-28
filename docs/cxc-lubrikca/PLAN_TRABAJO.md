# Plan de Trabajo — Subproyecto **CxC Lubrikca** sobre Omni

> Rama: `feature/cxc-lubrikca` (nace de `origin/develop`)
> App nueva dedicada: `backend/apps/cxc_lubrikca` (aislada; no modifica Omni core)
> Estado: **Fases 0–6 implementadas** (backend `apps/cxc_lubrikca` aislada + motor
> determinístico portado + captura/bandeja/conciliación + sync Odoo solo-lectura + frontend
> perfil `cobranza`), con gate verde por fase. **Fase 7 (go-live)** en
> [`CHECKLIST_GO_LIVE.md`](CHECKLIST_GO_LIVE.md): pasos de carga de config real y validación
> contra el Odoo real son acción del **owner** (requieren acceso a producción).

---

## 1. Objetivo

Llevar a producción, para **Lubrikca**, un sistema determinístico de **cobros,
descuentos y conciliación** que vive **dentro de Omni** como una **app dedicada y
aislada**, reutilizando la infraestructura de Omni (auth, tasas, Integration Hub,
frontend) **sin alterar la lógica de negocio del core de Omni**.

Consolida tres fuentes de trabajo previo:

| Fuente | Qué aporta |
|---|---|
| **CxC_Lubrikca** (repo propio, ~94% tests) | Motor determinístico + conciliación (lógica pura portable) |
| **GestionCxC** (FastAPI + Odoo, sistema real previo) | Config del motor **desde UI** + flujo de aprobación por roles + límites por producto |
| **Omni** (este repo) | Auth JWT/roles, tasas BCV+Binance, Integration Hub (Odoo), abonos/ledger, frontend React/MUI, perfil `cobranza` standalone |

---

## 2. Arquitectura y restricciones (confirmadas)

1. **Odoo = fuente de verdad.** Lubrikca opera sobre Odoo. No se reemplaza.
2. **Omni = aliado/soporte.** El **Integration Hub** lee Odoo (inbound,
   Odoo→Omni). **Omni NUNCA escribe a Odoo** (push outbound D3 diferido,
   [CTF-011]). **Google Sheets se descarta.** La data vive en Odoo y se replica a Omni.
3. **Aislamiento:** todo el dominio Lubrikca vive en **`apps/cxc_lubrikca`**
   (app nueva), feature-flagged por el perfil `cobranza`. Solo **lee** de las apps
   de Omni (`cuentas_por_cobrar`, `finanzas`, `integration_hub`); **no modifica**
   su lógica. Si una pieza necesitara algo del core, se hace por extensión, no por
   edición.
4. **Sin MVP iterativo:** se construye TODO, se prueba, se **configura en
   producción** y se valida contra el Odoo real, y **recién entonces** se arranca
   la operación. No hay fase de prueba en vivo con usuarios.

### Andamiaje que Omni YA tiene (reutilizar tal cual)

- `clients/cobranza-standalone` (**ADR-008 / Plan D**): distribución standalone de
  Cobranza para Lubrikca. D1 desacople ledger ✅ · D2 conexión Odoo + sync ✅ ·
  **D3 push a Odoo diferido ✅** · D4 shell frontend (`VITE_APP_PROFILE=cobranza`) ✅.
- `integration_hub/connectors/odoo` (XML-RPC inbound) y `.../tasas_ve`
  (scraper BCV cascada + Binance P2P 5+5), modelo `finanzas.TasaCambio`.
- `core` (auth JWT, roles, multi-tenant), `cuentas_por_cobrar` (`AbonoCxC`,
  `registrar_abono` atómico con asiento contable), `cxc` (cobranza inteligente).

---

## 3. Qué construir (gap real)

Omni **no** tiene el motor determinístico ni su control. Eso es lo nuevo:

- ❌ Disparador **neto-objetivo** (no nominal) y **apilamiento aditivo**.
- ❌ **Reselección de lista por método/ruta** (gana sobre lista especial).
- ❌ **Contado por ventana de días hábiles** (saltando fines de semana + feriados),
  anclado a la **entrega completa**; vencido → crédito.
- ❌ **BCV-completo** con **tasa diaria de gerencia topada al diferencial real**.
- ❌ **Equivalentes congelados por abono** (USD/VES a tasa estampada; antifraude).
- ❌ **Regla de mezcla → Binance** (ruta mixta pierde BCV-completo).
- ❌ **Primera compra = producto promo configurable** (precio de la lista de
   nacimiento de la SO).
- ❌ **Devoluciones**: facturar sobre cantidad entregada neta (opción D) + seguimiento.
- ❌ **Cierre híbrido** (motor marca candidata, humano confirma).
- ❌ **Semáforo de conciliación** motor-vs-factura real (USD vía tasa de la factura).
- ❌ **Config del motor desde UI** (límites, descuentos, promos, tasa diaria) — rescate GestionCxC.
- ❌ **Bandeja de aprobación por roles** (vendedor propone → gerente/admin confirma).

---

## 4. Fases de trabajo

### Fase 0 — Diseño e integración (destraba todo)
- **ADR del subproyecto** en `docs/decisions/` (app dedicada, aislamiento,
  feature-flag, read-only Odoo).
- Scaffold `apps/cxc_lubrikca` siguiendo convención Omni (models/, services/,
  api/, serializers, urls, tests, README) + alta en settings/router gated por perfil.
- **Mapa de datos:** qué entidades trae hoy el Integration Hub desde Odoo vs. lo
  que el motor necesita. Reutilizar el mapeo Odoo-18 ya resuelto
  (`CxC_Lubrikca/docs/ODOO_MAPEO.md`):
  - SO por `name`; vendedor = `user_id.login`; `pricelist_id` (4 USD / 5 BCV).
  - Líneas con **marca** (`product.brand_id`) y **categoría** (raíz de `categ_id`).
  - **Entrega completa** (`delivery_status=full`) → ancla del plazo; `qty_delivered`.
  - **Devoluciones** (pickings con `return_id`).
  - Factura USD (`amount_total_signed_usd`, la compañía factura en VES).
- **Entregable:** lista de gaps del conector Odoo de Omni + ADR + app scaffold con CI verde.

### Fase 1 — Config del motor desde UI (rescate GestionCxC)
- Modelos config con **effective dating**: `DescuentoMarcaCategoria`,
  `DescuentoBCVCompleto` (tasa diaria gerencia), `PromocionPrimeraCompra`,
  `ReglaRecurrencia` (recompra %), `Feriado`, `LimiteDescuentoProducto`,
  `CondicionNotaCredito`.
- DRF CRUD + admin + **pantallas de administración (MUI)** amigables.
- **Entregable:** el usuario administra todas las reglas desde la UI, con vigencias.

### Fase 2 — Motor determinístico (port de CxC_Lubrikca)
- Portar lógica pura a `apps/cxc_lubrikca/services/motor/`:
  `business_days`, `effective_dating`, `equivalents`, `discounts`, `reconcile`.
- Adaptar la capa de datos: dataclasses → modelos Omni/Odoo-synced.
- **Equivalentes congelados por abono** → extender `AbonoCxC`/`Pago` (por extensión).
- **Portar los tests** (~94%) a pytest de Omni con aislamiento multi-tenant.
- **Entregable:** motor calcula el neto esperado por orden; tests verdes.

### Fase 3 — Captura + aprobación (rescate GestionCxC + cierre híbrido)
- Vinculación pago↔orden (abonos) con validaciones (cliente, saldo, monto).
- **Sello de hora** contra la serie de tasas de Omni (bucket horario).
- **Bandeja de aprobación** por roles (hoy `gestion_aprobaciones` es scaffold):
  vendedor/Administración propone, gerente/admin confirma. **Sin escribir Odoo.**
- **Entregable:** flujo humano completo con cierre híbrido.

### Fase 4 — Conciliación (port)
- Semáforo motor-vs-factura real (USD vía `amount_total_signed_usd`),
  tolerancias configurables → verde/amarillo/rojo.
- Seguimiento visual de devoluciones y cartera atascada (DSO).
- **Entregable:** tablero de desviaciones.

### Fase 5 — Integración Odoo (solo lectura)
- Extender el conector Odoo de Omni para traer todo lo que el motor necesita
  (líneas marca/categoría, `delivery_status`, `qty_delivered`, devoluciones,
  facturas USD). Mapeo ya resuelto. **Cero escritura a Odoo.**
- Sync programado (Omni ya tiene D2).
- **Entregable:** datos completos y frescos en Omni para el motor.

### Fase 6 — Frontend (perfil cobranza)
- Pantallas: dashboard, config del motor, captura/vinculación, bandeja de
  aprobación, semáforo de conciliación, cartera/devoluciones. Rutas + hooks
  (TanStack Query) + schemas (zod), montadas solo en perfil `cobranza`.
- **Entregable:** app cobranza standalone usable de punta a punta.

### Fase 7 — Preparación a producción (sin MVP)
- Suite verde + cobertura ≥ umbral de Omni; CI del repo en verde.
- **Cargar la config real en producción** (límites, descuentos, promo, tasa diaria,
  feriados, métodos).
- **Validar contra el Odoo real de Lubrikca** (D2: `configurar_conector_odoo` +
  `validar_conector_odoo`).
- Checklist de go-live. **Recién aquí** se arranca la operación.

---

## 5. Convenciones (Omni)

- **Backend API-first:** `models/` → `serializers` → `views`/ViewSets (auth +
  `get_queryset()` por empresa) → `urls`/router → `services` (`@transaction.atomic`,
  locks) → `tests` (incluye test de aislamiento multi-tenant).
- **Frontend:** `pages/CxcLubrikca/*`, `routes/cxcLubrikcaRoutes.tsx`,
  `services/`, `hooks/`, `schemas/` (zod); gating por `appProfile.ts`.
- **Aislamiento:** la app nueva no edita apps core; consume sus modelos por lectura
  o por extensión explícita.

---

## 6. Decisiones / riesgos abiertos

- **Recálculo por devolución:** confirmado opción D (factura sobre
  `cantidad_entregada` si entrega completa + devolución). Listo en la lógica portada.
- **Precio lista USD en Odoo 18:** `price_get` removido; para ruta BCV/VES se usa
  el precio de la línea ya sincronizado. Para ruta USD definir método con Odoo.
- **Aislamiento real del ledger:** validar que `cxc_lubrikca` puede operar sin
  tocar `cuentas_por_cobrar` core (D1 ya desacopló el FK cliente).
- **Multi-tenant:** Lubrikca = una empresa; respetar `get_queryset()` por empresa.

---

## 7. Definición de "hecho" (Definition of Done)

- [x] App `cxc_lubrikca` aislada, feature-flagged, CI verde.
- [x] Motor + conciliación portados, con tests (paridad con CxC_Lubrikca).
- [x] Config del motor administrable 100% desde la UI.
- [x] Captura + bandeja de aprobación funcionando, sin escribir a Odoo.
- [x] Conector Odoo trae todo lo necesario (solo lectura) — **validación contra el Odoo real: owner** (ver checklist).
- [ ] Config de negocio **cargada en producción** — **owner** (requiere acceso a prod).
- [x] Checklist de go-live redactado ([`CHECKLIST_GO_LIVE.md`](CHECKLIST_GO_LIVE.md)).

---

## 8. Origen de cada pieza (trazabilidad)

| Pieza | Origen | Acción |
|---|---|---|
| Motor descuentos, conciliación, equivalentes | CxC_Lubrikca | **Portar** lógica + tests |
| Mapeo de campos Odoo 18 | CxC_Lubrikca (`docs/ODOO_MAPEO.md`) | **Reusar** en conector |
| Config UI (límites, condiciones, promos, tasas) + aprobación por roles | GestionCxC | **Rescatar/portar** patrón |
| Auth, tasas, Integration Hub, abonos/ledger, frontend, perfil cobranza | Omni | **Reusar** tal cual |
