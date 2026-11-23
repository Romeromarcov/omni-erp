# Plan 09 — Omni ERP Clase Mundial Adaptado al Mercado Venezolano

> Plan de ejecución maestro derivado de [`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md),
> el cierre al 100 % de [`08-conciliacion-pagos-y-paridad-odoo.md`](08-conciliacion-pagos-y-paridad-odoo.md)
> y la auditoría técnica en solo lectura sobre Odoo 18.0 Enterprise en operación venezolana
> (`Distribuidora Lubrikca, C.A.`, 247 módulos instalados + suite `l10n_ve_*` / `account_dual_currency`).
>
> **Propuesta de valor:** Igualar y superar la solidez transaccional de Odoo Enterprise manteniendo
> intactos los diferenciales de Omni ERP (**AI-Native REST + MCP**, **arquitectura trimonetaria y multi-tasa**,
> **operación y contabilidad dual Fiscal vs Gerencial**, **nómina dual VE**, **logística inteligente con IA/GPS**
> y **portales independientes**).

| Campo | Valor |
|---|---|
| **Estado** | **EN CURSO** — **Ola 1A (Motor Trimonetario y Multi-Tasa)** mergeada (`#318`); **Ola 6 (`#333–#337`)** completada ✅; **Ola 1B (Contabilidad Dual, Analítica, Perfil Fiscal VE y ND)** en ejecución (`R-PROC-2`) |
| **Fecha** | 2026-11-22 (sincronizado con `develop @ 61d2001`, cierre `#288–#320`) |
| **Apps involucradas** | `core`, `finanzas`, `contabilidad`, `tesoreria`, `fiscal`, `localizacion_ve`, `ventas`, `compras`, `inventario`, `almacenes`, `nomina`, `rrhh`, `control_asistencia`, `despacho`, `crm`, `proveedores`, `gestion_aprobaciones`, `personalizacion`, `configuracion_motor`, `agentes`, `integration_hub`, `migracion_datos` |
| **Gate de cierre** | [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md) + aislamiento multi-tenant + RLS + paridad REST/MCP/UI |

---

## 1. Síntesis de Auditoría Odoo 18 Enterprise (VE) vs Omni ERP (`develop @ f4f0965`)

### 1.1 Hallazgos clave en Odoo 18.0+e (Lubrikca QA1 — solo lectura)
- **Stack real:** Odoo 18 Enterprise + suite VE de Lixie Studio (`account_dual_currency`, `l10n_ve_full`, `l10n_ve_digital_invoicing`, `l10n_ve_setup`, `l10n_ve_payroll`, `lixie_credit_limit`, `lixie_lubrika_app`) + add-ons de terceros (`bi_sale_target_commission`, `product_brand_*`, `whatsapp_connector*`, `simplify_access_management`, `tk_security_master`).
- **Fortalezas a igualar:** Dualidad contable línea por línea (`debit_usd`/`credit_usd`/`tax_today`), retenciones IVA (`.txt` SENIAT) e ISLR (32 conceptos, `.xml` SENIAT), IGTF 3% + ITF, Imprenta Digital **Unidigital** para facturas y guías de despacho (`stock.picking`), Libro de Inventario Fiscal, perfil fiscal completo en `res.partner`, `costo_reposicion_usd` y flujo multi-almacén Pick-Pack-Ship + Barcode.
- **Dolores estructurales de Odoo en Venezuela (oportunidad de diferenciación de Omni ERP):**
  1. **10 listas de precios estáticas** (2,169 ítems manuales) duplicadas en pares `USD` vs `VES` (~53.8% de brecha cambiaria) por zona y segmento.
  2. **Solo 2 monedas** y 1 tasa por día; requiere **2 reglas `base.automation` como parches** para corregir la tasa BCV en pagos y estados de cuenta (Efectivo/Zelle/Binance).
  3. **Rigidez contable única:** no separa contabilidad fiscal de contabilidad gerencial (notas de venta, compras informales, inventario gerencial).
  4. **Nómina VE inoperante en práctica** (`hr.payslip = 0`): no resuelve el modelo real del 99% de las empresas venezolanas (nómina formal LOTTT + bonificaciones/efectivo gerencial).
  5. **Logística sin inteligencia:** sin ruteo IA, sin GPS nativo ni integración con apps de última milla (Uber/Ridery/Yummy) ni ePOD móvil.
  6. **Sin portales independientes** optimizados para vendedores en calle (SFA), clientes self-service (B2B/B2C) y conductores.

### 1.2 Semillas ya existentes en Omni ERP (`develop @ f4f0965`)
- `core.Empresa` ya posee `id_moneda_base` y `id_moneda_pais`.
- `finanzas` ya tiene `TasaCambio`, `AsignacionPago` N:M y `PagoTercero`.
- `contabilidad` ya tiene `DiarioContable`, `PeriodoContable`, cierre y reportes canónicos.
- `nomina` ya tiene `ProcesoNomina`/`Nomina` y `ProcesoNominaExtrasalarial`/`NominaExtrasalarial` + `control_asistencia`.
- `despacho` ya tiene `Despacho` y `DetalleDespacho`.
- `inventario`/`almacenes` ya tiene `OperacionInventario` stepper, FIFO/Promedio + COGS, `LoteProducto`, `StockUbicacion` y `ReglaReabastecimiento`.
- `localizacion_ve` ya tiene 6/6 puertos (`PR #312`).
- `core` + `personalizacion` ya tienen `Roles`, `Permisos`, `RolPermisos`, `UsuarioRoles` y `VistaPersonalizada`.

---

## 2. Pilares de Diseño

1. **Sistema Trimonetario Configurable y Multi-Tasa:**
   - **Moneda Base (`id_moneda_base`):** ej. `USD` — cálculos operativos y gerenciales.
   - **Moneda País / Cumplimiento (`id_moneda_pais`):** ej. `VES` — cumplimiento fiscal, contable y normativo usando tasa oficial (`OFICIAL_BCV`).
   - **Moneda de Referencia Adicional (`id_moneda_referencia`, activable/desactivable):** ej. `USDT` — tasa diaria configurable; todos los cálculos, documentos y reportes se expresan simultáneamente en **Base + País + Referencia**.
   - **Múltiples tasas por par:** modelo `TipoTasaCambio` extensible por tenant (ej. `OFICIAL_BCV`, `USDT`, `PARALELO`, `PROMEDIO`, `CONVENIDA`) sin `choices` hardcodeados.
2. **Operación y Contabilidad Dual (`FISCAL` vs `GERENCIAL`):**
   - `ambito_contable = FISCAL`: facturas fiscales, NC/ND fiscales, compras fiscales, nómina formal LOTTT, retenciones, IGTF, inventario fiscal → alimenta Libros SENIAT y Contabilidad Fiscal (VES/BCV).
   - `ambito_contable = GERENCIAL`: notas de venta que generan CxC sin factura fiscal ni libro de ventas, compras sin factura fiscal, inventario gerencial, nómina de bonificaciones/efectivo, gastos no deducibles → nunca contamina la contabilidad fiscal y consolida en la **Contabilidad Gerencial** (`FISCAL + GERENCIAL`) en las 3 monedas.
   - Opt-in por empresa en `configuracion_motor` y protegido estrictamente por permisos/roles + RLS + auditoría.

---

## 3. Fases de Ejecución

### Fase 1 — Motor Trimonetario, Multi-Tasa y Contabilidad Dual (`finanzas`, `contabilidad`, `core`, `tesoreria`)
- **1.1 Parametrización Trimonetaria y Multi-Tasa:**
  - `core.Empresa`: agregar `id_moneda_referencia` (FK nullable `finanzas.Moneda`) + `usar_moneda_referencia` (`BooleanField`, default `False`).
  - `finanzas.TipoTasaCambio` (con RLS): catálogo por empresa (`codigo`, `nombre`, `es_oficial_fiscal`, `activa`), referenciado desde `finanzas.TasaCambio`.
  - Servicio canónico `calcular_equivalencias_trimonetarias(monto, moneda, fecha, empresa, tipo_tasa_ref=...)` (`Decimal` estricto).
  - Corrector automático nativo de tasa BCV para diarios/métodos en divisa (`Efectivo USD`, `Zelle`, `Binance`).
- **1.2 Contabilidad Dual (`FISCAL` / `GERENCIAL`) y Trimonetaria:**
  - Campo `ambito` (`FISCAL` | `GERENCIAL`) en `DiarioContable`, `AsientoContable`, `NotaVenta`, `FacturaCompra`, `MovimientoInventario`, `ProcesoNomina` y `Gasto`.
  - En `DetalleAsiento`: persistir importes inmutables en 3 monedas (`debe_pais`/`haber_pais`, `debe_base`/`haber_base`, `debe_referencia`/`haber_referencia`, `tasa_bcv_aplicada`, `tasa_referencia_aplicada`).
  - Reportes contables (P&L, Balance General, Mayor, Comprobación) con filtros **Libro (`FISCAL` | `GERENCIAL` | `CONSOLIDADO`)** y **Moneda (`PAIS` | `BASE` | `REFERENCIA`)**.
- **1.3 Contabilidad Analítica y Pre-Conciliación Bancaria VE:**
  - `CentroCosto` / `EtiquetaAnalitica` en apuntes y documentos.
  - Motor de cruce automático extracto ↔ `Pago`/`PagoTercero` (Banesco, Mercantil, BDV, BNC, Provincial, Bancamiga, Zelle, Binance, Pago Móvil).

### Fase 2 — Blindaje Fiscal Venezolano 360° (`fiscal`, `localizacion_ve`, `ventas`, `compras`, `core`)
- **2.1 Perfil Fiscal VE en `core.Contacto`:** `tipo_contribuyente`, `tipo_persona_fiscal` (`PNR`/`PNNR`/`PJDO`/`PJND`), `es_agente_retencion_iva`, `porcentaje_retencion_iva`, `es_agente_retencion_islr`, `exento_islr`, `estado`, `municipio`.
- **2.2 Notas de Débito Fiscales:** `ventas.NotaDebitoFiscal` + `compras` con correlativo, asiento en diario `NDCLI` (`FISCAL`), afectación CxC/CxP y Libros SENIAT.
- **2.3 Retenciones IVA e ISLR + Exportadores SENIAT:**
  - IVA: comprobante PDF + exportación **`.txt` SENIAT** + asientos `IVAV`/`IVAC` + conciliación vía `AsignacionPago`.
  - ISLR: catálogo precargado de **32+ conceptos Decreto 1808** (tasas y sustraendo UT) + comprobante PDF + exportación **`.xml` SENIAT**.
  - IGTF 3% Divisa e ITF bancario con desglose y asiento automático separado.
- **2.4 Imprenta Digital SENIAT (Providencia 000102/000121):** puerto `ProveedorImprentaDigital` en `localizacion_ve` con primer adaptador **Unidigital** (extensible a The Factory HKA) para Facturas, NC, ND y **Guías de Despacho**.
- **2.5 Libro de Inventario Fiscal (Art. 177 LISLR):** reporte mensual/anual sobre `ambito=FISCAL` en `moneda_pais`.

### Fase 3 — Motor Comercial Venezolano (`ventas`, `crm`, `finanzas`)
- **3.1 Motor Dinámico de Precios por Moneda de Pago / Brecha Cambiaria:** reglas componibles (`Precio Base USD` × `Zona/Ruta` × `Factor Moneda de Pago [Divisa / Bs BCV / USDT]` × `Segmento/Volumen`), eliminando listas duplicadas manuales y mostrando totales en **USD / VES BCV / USDT**.
- **3.2 Flujo Dual Notas de Venta Gerenciales vs Facturas Fiscales:** `NotaVenta` (`GERENCIAL`) genera CxC real sin tocar libros fiscales ni contabilidad formal, con acción opcional de fiscalización.
- **3.3 Control de Crédito Inteligente, Aprobaciones y Comisiones:** límite de crédito USD + bloqueo por mora real (`AsignacionPago`) + excepción vía `gestion_aprobaciones`; comisiones por meta y **cobro efectivo** (diferenciando divisa vs Bs).
- **3.4 POS Táctil Offline Completo (Cierre `CTF-008`):** `PosPage` integrado a `salesOutbox` + `POST /api/sync/push/ventas/`, pagos mixtos multimoneda + vuelto + IGTF + impresora térmica 80mm.

### Fase 4 — Nómina Dual Venezolana (`nomina`, `rrhh`, `control_asistencia`, `tesoreria`)
- **4.1 Ficha Salarial Dual y Motor de Paquete Objetivo:**
  - Capa Formal LOTTT (`ambito=FISCAL`: salario base Bs, cestaticket BCV, AR-I, carga familiar) + Capa Gerencial/Bonificaciones (`ambito=GERENCIAL`: paquete objetivo USD/USDT o bonos fijos/variables).
  - Cálculo automático del diferencial (`Bono Gerencial = Paquete Objetivo − Equivalente Formal`) en un solo proceso sin Excel paralelo.
- **4.2 Cumplimiento Legal LOTTT Completo:** IVSS (SSO), RPE, FAOV (1%/2%), INCES (2%/0.5%), ISLR progresivo, LOPCYMAT; provisiones automáticas de Prestaciones Sociales (garantía trimestral + días adicionales + intereses BCV), Vacaciones + Bono Vacacional, Utilidades y Simulador de Liquidación.
- **4.3 Exportadores Bancarios/Parafiscales, Pagos Multimoneda y Préstamos:**
  - TXT bancarios VE (`BANESCO_TXT`, `MERCANTIL_TXT`, `BDV_TXT`) y exportadores FAOV/Tiuna/INCES/ISLR.
  - Dispersión de bonificaciones en **Efectivo USD (con arqueo de denominaciones)**, Zelle, Binance/USDT y Pago Móvil.
  - Préstamos/adelantos con amortización configurable, integración con `control_asistencia`, recibos separados/consolidados (PDF por WhatsApp/email) y asientos segregados (`FISCAL` vs `GERENCIAL`).

### Fase 5 — Supply Chain, Importaciones e Inventario Inteligente (`compras`, `inventario`, `almacenes`)
- **5.1 Costos en Destino (`Landed Costs`):** prorrateo de flete, seguro, arancel y nacionalización (`nro_expediente_impor`, `nro_planilla_impor`) por valor/peso/volumen/cantidad sobre `ValoracionInventario` con asiento automático.
- **5.2 Costo de Reposición USD/USDT y Semáforo de Margen Real:** `costo_reposicion_usd` en `Producto` + alertas en ventas cuando el margen real sobre reposición baja del mínimo.
- **5.3 Inventario Dual (`FISCAL` vs `GERENCIAL`) y Conteo Físico Cíclico:** sesiones guiadas desde `/escaner` con aprobación de diferencias y ajuste contable.
- **5.4 Barcode en Stepper Pick-Pack-Ship + Tránsito Inter-Almacén + 3-Way Matching:** `/escaner` conectado a `OperacionInventario`, ubicación de tránsito entre sedes y validación automática `OC ↔ Recepción ↔ FacturaCompra`.

### Fase 6 — Logística Inteligente y Despacho TMS (`despacho`, `almacenes`, `ventas`, `agentes`)
- **6.1 Geolocalización de Clientes y Maestro de Flota:** coordenadas GPS (`lat`, `lng`), pin en mapa y ventanas de entrega en `crm.DireccionCliente`/`core.Contacto`; modelos `Vehiculo`, `Conductor`, `ZonaLogistica`, `RutaDespacho`, `ParadaEntrega`, `TarifaFlete`.
- **6.2 Optimizador de Rutas con IA (VRP):** asignación automática de pedidos a vehículos por capacidad (kg/m³/paletas/litros), zona, tráfico y ventanas horarias → secuencia óptima de paradas y ETA.
- **6.3 Integración con Mapas y Apps de Delivery (estilo Uber):** puerto `ProveedorDeliveryExterno` (adaptadores **Uber Direct**, **Ridery**, **Yummy/mensajería**) para cotización, solicitud de unidad y tracking en vivo; torre de control en mapa en tiempo real.
- **6.4 Prueba de Entrega Digital (ePOD), Cobro en Sitio y Tracking WhatsApp:** foto de entrega + firma digital + sello GPS, entrega parcial/rechazo ligado a devoluciones, cobro contra entrega ligado a `finanzas.Pago`, link público de tracking en vivo por WhatsApp y emisión de **Guía de Despacho Digital SENIAT** desde la ruta.

### Fase 7 — Gobierno Granular (RBAC/ABAC) y Portales Independientes (`core`, `personalizacion`, `frontend`)
- **7.1 Matriz Visual RBAC/ABAC ("Access Studio" nativo):** permisos por `Módulo × Acción × Ámbito (FISCAL/GERENCIAL) × Alcance (propio/sucursal/almacén/empresa)` + ocultamiento de campos sensibles (costos, márgenes, nómina gerencial) + 2FA, control de sesiones y auditoría inmutable.
- **7.2 Módulo/App Independiente para Vendedores (SFA):** cartera propia, catálogo con stock y precios trimonetarios, cotizaciones/pedidos offline-capable, CxC/mora de sus clientes, carga de cobros con foto, check-in GPS y tablero de metas/comisiones.
- **7.3 Portal/App Independiente para Clientes (B2B/B2C):** login o WhatsApp OTP; historial de compras (facturas y notas), estado de cuenta en **USD/VES/USDT**, descarga de PDFs/retenciones, **carga de pagos** (con OCR/IA de comprobantes), **realización de pedidos** y tracking en vivo de despachos.
- **7.4 App Independiente de Logística / Conductores:** lista de paradas optimizada por IA, navegación 1-tap (Waze/Google Maps), escaneo de bultos, ePOD (foto/firma/GPS) y cobro contra entrega con tolerancia offline.

### Fase 8 — Omnicanalidad WhatsApp, Agentes IA Operativos, Hardening Prod y Migración 1-Click Odoo
- **8.1 Chatter + WhatsApp Business en Documentos:** historial y envío directo de cotizaciones, cobranza y tracking.
- **8.2 Agentes IA Operativos:** Cobranza, Tesorero (pre-conciliación Zelle/Pago Móvil), Logístico (re-ruteo), Comprador (reabastecimiento) y CFO Copilot Trimonetario.
- **8.3 Hardening Producción (Owner/Infra):** activación `RLS_ENABLED=True` con rol `omni_app` (`CTF-012`), backups con restore probado (`P1-7`), firma Electron/Android (`CTF-010`).
- **8.4 Migrador 1-Click desde Odoo (y Saint/Profit/Galac):** reaprovechar `OdooConnector` + `migracion_datos` para importar Plan de Cuentas, Contactos fiscales, Productos/Marcas/Costos, Stock y saldos CxC/CxP.

---

## 4. Secuenciación Recomendada por Olas (PRs Focales `R-PROC-2`)

| Ola | Fases / PRs sugeridos | Estado / Dependencia |
|---|---|---|
| **Ola 1A (P0)** | **Fase 1.1** (Motor Trimonetario + `TipoTasaCambio` extensible con RLS + `es_moneda_referencia` + REST/MCP) | ✅ **COMPLETADA (`#318`)** |
| **Ola 6 (Consolidación)** | **PR-31..PR-35** (`docs/mypy/ruff/TZ` → `strangler-fig l10n` en `fiscal`/`ventas`/`nomina` → `POST /api/sync/push/` optimista `CTF-008` → `SAAS_FAIL_CLOSED` + 2FA TOTP `Plan 05 P3-1` → smoke test live QA Connect→Odoo `crm.lead`) | ✅ **COMPLETADA (`#333–#337`)** |
| **Ola 1B-1 (P0)** | **Fase 1.2** (Contabilidad Dual `FISCAL`/`GERENCIAL` + Analítica `CentroCosto` + Reportes comparativos) | ✅ **COMPLETADA (`#338`)** |
| **Ola 1B-2 (P0)** | **Fase 1.2 + 2.1–2.2** (`ambito` en documentos origen + exclusión SENIAT + Perfil fiscal VE `core.Contacto` + `NotaDebitoFiscal` + MCP/Libros) | ✅ **COMPLETADA (`#339`)** |
| **Ola 2A (P0)** | **Fase 3.1–3.3** (Precios dinámicos por brecha + Flujo dual Nota Venta Gerencial + Crédito por mora real + Comisiones por cobro efectivo y metas + MCP) | ✅ **COMPLETADA (`#340`)** |
| **Ola 2B (P0)** | **Fase 7.1** (RBAC/ABAC Granular por módulo × acción × ámbito × alcance + Access Studio UI/API) | 🔄 **EN CURSO (PR-39)** |
| **Ola 3 (P1)** | **Fase 2.3–2.5** (Retenciones IVA `.txt`/ISLR `.xml` + Imprenta Digital Unidigital + Libro Inv.) + **Fase 4** (Nómina Dual VE LOTTT + Bonificaciones) | Ola 1 |
| **Ola 4 (P1)** | **Fase 6** (Logística TMS IA/GPS/Delivery/ePOD) + **Fase 5** (Landed Costs + Costo Reposición + Conteo Físico + Barcode) | Ola 1 + Ola 2 |
| **Ola 5 (P2)** | **Fase 7.2–7.4** (Portales independientes: Vendedores SFA, Clientes Self-Service, Conductores) + cierre operativo campo `CTF-008` | Ola 2 + Ola 4 |
| **Ola 6B / Fase 8 (P2/P3)** | **Fase 8** (WhatsApp/Chatter, Agentes IA operativos, RLS prod `CTF-012` + firma apps `CTF-010`, Migrador 1-Click Odoo) | Ola 3 + Ola 5 |

Cada PR deberá cumplir íntegramente [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md) (`check`, `makemigrations --check --dry-run`, `mapa_superficie --check`, tests multi-tenant + RLS y `diff-cover ≥ 95 %`, `tsc -b`, `npm run lint`, `check:api-drift`, Vitest/Playwright) y recibir dictamen **`APROBADO`** de revisor independiente (`QA + Seguridad`) antes de merge a `develop`.
