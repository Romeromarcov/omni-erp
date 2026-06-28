# Mapa de datos y gaps del conector Odoo — CxC Lubrikca (Fase 0)

> Entregable de la **Fase 0** (PLAN_TRABAJO.md §4). Cruza lo que el **motor
> determinístico** necesita (según `CxC_Lubrikca/docs/ODOO_MAPEO.md` y la
> especificación) contra lo que el **conector Odoo de Omni**
> (`apps/integration_hub/connectors/odoo`) trae hoy. Define qué se cierra en
> **Fase 5** por **extensión** del conector (solo lectura, cero escritura a Odoo).

## 1. Constantes Odoo de Lubrikca (QA real)

| Concepto | Modelo Odoo | ID real | Nota |
|---|---|---|---|
| Moneda USD | `res.currency` | 1 | — |
| Moneda VES | `res.currency` | 166 | símbolo `Bs` |
| Lista "USD" | `product.pricelist` | 4 | currency USD |
| Lista "Precio USD Pago VES" (BCV) | `product.pricelist` | 5 | currency USD |
| Marcas | `product.brand` | Global Oil (1), Sinoco (2), Master (3) | 🚩 solo 8/255 productos con marca |
| Categorías raíz | `product.category` | Comercial (4), Industrial (5) | árbol |
| Métodos de pago | `account.journal` | 29 USD efvo, 15 Bs efvo (BCV), 14/30/31/32/33 bancos VES (BCV) | journal_id → MetodoPago |

## 2. Tabla de gaps (motor ⟷ conector Omni)

Estado del conector tomado de la recon Fase 0
(`pull_pedidos_venta`, `pull_facturas_venta`, `pull_pagos`, `pull_cartera_vencida`,
`pull_pagos_cliente`).

| # | Dato que el motor necesita | Campo Odoo | ¿Lo trae Omni hoy? | Gap / acción Fase 5 |
|---|---|---|---|---|
| 1 | SO por nombre | `sale.order.name` (`S00553`) | ✅ `pull_pedidos_venta` | — |
| 2 | Cliente de la SO | `sale.order.partner_id` | ✅ | — |
| 3 | Fecha de orden | `sale.order.date_order` | ✅ | — |
| 4 | Lista de precios de la SO | `sale.order.pricelist_id` (4/5) | ✅ | — |
| 5 | Vendedor | `sale.order.user_id.login` | ⚠️ trae `user_id` | **Gap:** resolver `.login` (email). Extender mapeo. |
| 6 | Monto total SO | `sale.order.amount_total` | ✅ | — |
| 7 | **Estado de entrega** | `sale.order.delivery_status` (`full`/`partial`/`pending`) | ❌ | **Gap crítico:** ancla del plazo de contado. Añadir al pull. |
| 8 | **Fecha de entrega completa** | `stock.picking.date_done` (outgoing) | ❌ | **Gap crítico:** no usar `commitment_date`. Pull de pickings. |
| 9 | **Cantidad entregada (neta)** | `stock.move.qty_done` / `qty_delivered` | ❌ | **Gap:** para devoluciones opción D. |
| 10 | **Líneas con marca** | `product.product.brand_id` | ❌ (productos traen `categ_id`, no brand) | **Gap:** descuento por marca×categoría. 🚩 normalizar en Odoo primero. |
| 11 | **Líneas con categoría raíz** | `product.category` (raíz del árbol) | ⚠️ `pull_productos` trae `categ_id` | **Gap parcial:** resolver raíz del árbol (Comercial/Industrial). |
| 12 | Línea: producto/cantidad/precio | `sale.order.line.*` | ✅ `pull_pedidos_venta` (con líneas) | — |
| 13 | **Devoluciones** | `stock.picking.return_id` | ❌ | **Gap:** seguimiento de devoluciones (opción D). |
| 14 | Factura por origen | `account.move` con `invoice_origin = SO.name` | ✅ `pull_facturas_venta` | — |
| 15 | **Monto facturado en USD** | `account.move.amount_total_signed_usd` | ❌ (trae `amount_total` en VES) | **Gap crítico:** conciliación motor-vs-factura en USD. |
| 16 | Notas de crédito | `account.move` (`out_refund`) | ⚠️ verificar filtro | **Gap parcial:** asegurar pull de `out_refund` para neto. |
| 17 | Pagos: monto/moneda/fecha/journal | `account.payment.*` | ✅ `pull_pagos` / `pull_pagos_cliente` | — |
| 18 | Pago ↔ facturas conciliadas | `account.payment.reconciled_invoice_ids` | ✅ `pull_pagos` | — |
| 19 | Es primera compra | COUNT(SO) por `partner_id` = 1 | ⚙️ derivable en Omni | Calcular en motor (no es gap de conector). |

Leyenda: ✅ disponible · ⚠️ parcial / requiere ajuste · ❌ falta (gap real).

## 3. Tasas (ya disponibles en Omni)

- `finanzas.TasaCambio` con `tipo_tasa`: `OFICIAL_BCV` (BCV) y `PROMEDIO_MERCADO`
  (Binance P2P). Lookup por `(tipo_tasa, moneda_origen, moneda_destino, fecha_tasa,
  hora_tasa)`. Conector `tasas_ve`: cascada BCV (dolarapi → exchangedynamic →
  bcv.org.ve) + Binance P2P (5 compra + 5 venta, promedio).
- **Extensión necesaria (Fase 2/3):** equivalentes **congelados por abono**.
  `AbonoCxC` **no** estampa tasa hoy → se añade por **extensión** (modelo propio
  en `cxc_lubrikca` que referencia el abono y guarda las 4 equivalencias USD/VES
  congeladas al bucket horario de la hora de pago confirmada). Antifraude.

## 4. Resumen de gaps a cerrar en Fase 5 (extensión del conector, solo lectura)

1. `delivery_status` + `stock.picking.date_done` (entrega completa → ancla del plazo). **[crítico]**
2. `qty_delivered` / `stock.move.qty_done` + devoluciones por `return_id`. **[devoluciones opción D]**
3. `product.brand_id` en líneas + resolución de categoría raíz. **[descuento marca×categoría]**
4. `amount_total_signed_usd` de la factura + notas de crédito `out_refund`. **[conciliación en USD]**
5. `user_id.login` (email del vendedor). **[bandeja de aprobación por roles]**

Riesgo conocido (de `CxC_Lubrikca/TODO.md`): Odoo 18 removió `price_get()`; para la
ruta USD definir método de precio con Odoo. Para ruta BCV/VES se usa el precio de
la línea ya sincronizado.

## 5. Aislamiento confirmado

- Plan D ya entregó: D1 (FK cliente desacoplado, `cliente_externo_id`), D2 (conexión
  Odoo + sync vía `configurar_conector_odoo`/`validar_conector_odoo`), D4 (shell
  frontend perfil `cobranza`). D3 (push a Odoo) **diferido** [CTF-011].
- `cxc_lubrikca` consume el conector y el ledger **por lectura/extensión**; no edita
  su lógica.
