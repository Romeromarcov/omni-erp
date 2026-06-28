# Checklist de Go-Live — CxC Lubrikca

> Estado del código: **Fases 0–6 completas** (app `apps/cxc_lubrikca` aislada + frontend
> perfil `cobranza`), con gate verde por fase. Este checklist cubre la **Fase 7**: lo que
> falta para arrancar la operación real. Los pasos marcados **owner** requieren acceso a
> producción / al Odoo real de Lubrikca y **no son automatizables** por un agente.

## 1. Despliegue del código

- [x] PR `feature/cxc-lubrikca` → `develop` con **CI verde** (autoaprobable, R-PROC-3).
- [ ] Validación en **staging** (Railway despliega `develop` al merge).
- [ ] **owner** PR `develop` → `main` con **revisión humana** del owner → producción.

La app es **additiva y aislada** (ADR-013): no modifica el core. El frontend de cobranza
se activa por build `VITE_APP_PROFILE=cobranza` (`npm run build:cobranza`). Rollback =
no exponer el módulo `cxc-lubrikca` / revertir el merge; no hay migraciones destructivas.

## 2. Configurar el conector Odoo (solo lectura) — D2

**owner** (requiere credenciales del Odoo real de Lubrikca):

```bash
cd backend
python manage.py configurar_conector_odoo \
  --empresa <empresa_id_or_rif> \
  --host https://lubrikca.odoo.com --db <db> --user <api_user> --api-key <SECRET> \
  --datasource-odoo --test
python manage.py validar_conector_odoo --empresa <empresa_id_or_rif>
```

## 3. Cargar la configuración del motor (desde la UI o API)

**owner** (valores reales de negocio). Pantalla **CxC Lubrikca → Config del Motor**, o API:

- [ ] **Descuentos marca×categoría** (`/api/cxc-lubrikca/descuentos-marca-categoria/`):
  Sinoco 3 %, Global Oil sintético 8 %, Global Oil industrial 6 %, … (porcentaje en
  **fracción**: 3 % → `0.03`), con `vigencia_desde`.
- [ ] **Descuento BCV-completo** (`/descuentos-bcv-completo/`): tasa diaria de gerencia
  (se topa al diferencial real binance/bcv por abono).
- [ ] **Promoción primera compra** (`/promociones-primera-compra/`): producto-promo.
- [ ] **Reglas de recurrencia** (`/reglas-recurrencia/`): recompra (p. ej. 3 %).
- [ ] **Feriados** (`/feriados/`): tabla para la ventana de días hábiles de contado.
- [ ] **Métodos de pago** (`/metodos-pago/`): mapear journals Odoo (29 USD efvo, 15 Bs
  efvo BCV, 14/30/31/32/33 bancos VES BCV) → `codigo`, `moneda`, `tipo_tasa`, `es_contado`.
- [ ] **Tolerancias de conciliación** (`/config-conciliacion/`): redondeo y banda roja.
- [ ] **Tasas** (núcleo finanzas): asegurar carga diaria de `OFICIAL_BCV` y
  `PROMEDIO_MERCADO` (Binance P2P) vía conector `tasas_ve` (el motor estampa la tasa por
  fecha local de Caracas al vincular).

## 4. Sincronizar desde Odoo (espejo, solo lectura)

**owner**:

```bash
python manage.py sincronizar_cxc_lubrikca --empresa <empresa_id_or_rif>
```

Puebla `PedidoLubrikca`/`LineaPedidoLubrikca`/`PrecioListaLubrikca`/`PagoLubrikca` +
`monto_facturado`/`ncs_facturadas`. **Nunca** toca Vinculacion/Bandeja/Conciliacion ni
escribe a Odoo. Programar como tarea periódica (Omni ya tiene D2 con Celery).

## 5. Smoke tests post-config (staging/prod)

- [ ] `GET /api/cxc-lubrikca/health/` → `{"status":"ok"}`.
- [ ] Dashboard de cartera carga el resumen (semáforo, devoluciones, cartera atascada).
- [ ] Config del Motor: alta/edición de una regla con vigencia se persiste.
- [ ] Captura: registrar una vinculación pago↔pedido estampa tasas y congela equivalentes;
  recalcular produce la BandejaFacturacion (neto del motor).
- [ ] Bandeja: una orden candidata se propone y un gerente/admin la confirma (cierre híbrido).
- [ ] Conciliación: un pedido facturado da semáforo verde/amarillo/rojo según tolerancias.

## 6. Validación contra el Odoo real (sin MVP iterativo)

**owner**: validar el cálculo del motor contra facturas reales de Lubrikca (paridad con el
sistema previo CxC_Lubrikca) **antes** de arrancar la operación. Revisar especialmente:
marca/categoría de líneas (Odoo solo tiene marca en ~8/255 productos → normalizar en Odoo),
`amount_total_signed_usd` para conciliación en USD, y precios de lista 4 vs 5 (Odoo 18 sin
`price_get`; ver limitación en `MAPA_DATOS_GAPS.md §4`).

## 7. Deuda / pendientes conocidos

- Precios lista USD (4) vs BCV (5): hoy el sync usa el precio de la lista de la propia SO;
  poblar ambas listas requiere leer `product.pricelist.item` (mejora futura).
- Push a Odoo: **diferido** [CTF-011] (Omni nunca escribe a Odoo).
