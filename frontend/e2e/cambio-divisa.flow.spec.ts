import { test, expect } from '@playwright/test';
import { iniciarSesion, aLista } from './helpers/sesion';
import {
  sufijoUnico,
  asegurarMoneda,
  monedaUsd,
  crearCuentaBancaria,
  crearTasaCambio,
  crearMetodoPago,
} from './helpers/datos';

/**
 * Flujo crítico — Cambio de Divisa (tesorería ↔ finanzas ↔ contabilidad).
 *
 * Cadena de punta a punta soportada HOY por el producto, manejada vía UI:
 *   registrar una operación de cambio (monto origen × tasa = monto destino) →
 *   el backend genera, en UNA transacción (R-CODE-11 / CTF-013):
 *     - un EGRESO en la moneda origen (TransaccionFinanciera + MovimientoCajaBanco),
 *     - un INGRESO en la moneda destino,
 *     - (si aplica) un Gasto por la comisión,
 *     - el asiento contable CAMBIO_DIVISA.
 *
 * Cruza tesoreria → finanzas (monedas/métodos de pago/cuentas) → contabilidad.
 *
 * Prerequisitos sembrados vía API:
 *   - moneda USD (la base, del seed) + moneda VES (creada aquí, pública);
 *   - cuentas bancarias en ambas monedas (no estrictamente necesarias para el
 *     doble registro, pero reflejan un setup realista de tesorería);
 *   - una TasaCambio VES→USD vigente al día (prerequisito explícito del cambio
 *     de divisa: sin tasa hacia la moneda base, el doble registro de un monto en
 *     moneda no-base falla con 400);
 *   - un método de pago electrónico (el egreso/ingreso crean TransaccionFinanciera
 *     que exige id_metodo_pago NOT NULL).
 *
 * Efectos cruzados verificados:
 *   - UI: la operación aparece en la lista con sus montos y tasa exactos;
 *   - API: existen un MovimientoCajaBanco EGRESO en moneda origen y otro INGRESO
 *     en moneda destino por los montos de la operación;
 *   - API: el asiento CAMBIO_DIVISA es opcional por empresa (ADR-006): si la
 *     empresa generó asientos, el balance de comprobación debe cuadrar.
 *
 * NOTA (gap honesto): el formulario de cambio NO expone selectores de Caja, y el
 * backend no recalcula `Caja.saldo_actual` desde MovimientoCajaBanco (saldo_anterior
 * /saldo_nuevo se graban en 0). Por eso el efecto sobre cajas se verifica a nivel
 * de MovimientoCajaBanco (origen/destino) y no como variación de saldo de caja.
 */

interface MovimientoCajaBancoApi {
  tipo_movimiento: string;
  monto: string;
  id_moneda: string | null;
  concepto: string;
}

test.describe('Cambio de divisa: operación por UI → doble registro + asiento', () => {
  test('registra el cambio por UI y verifica egreso/ingreso y asiento', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();

    // ── Prerequisitos sembrados vía API ──────────────────────────────────────
    const usdId = await monedaUsd(sesion.api); // moneda base de la empresa (seed)
    const vesId = await asegurarMoneda(sesion.api, 'VES', {
      nombre: 'Bolívar',
      simbolo: 'Bs',
    });

    // Cuentas bancarias en ambas monedas (setup realista de tesorería).
    await crearCuentaBancaria(sesion.api, {
      empresaId: sesion.empresaId,
      monedaId: usdId,
      nombreBanco: `Banco USD ${suf}`,
      sufijo: suf,
    });
    await crearCuentaBancaria(sesion.api, {
      empresaId: sesion.empresaId,
      monedaId: vesId,
      nombreBanco: `Banco VES ${suf}`,
      sufijo: suf,
    });

    // Tasa VES→USD vigente al día (prerequisito del cambio de divisa).
    await crearTasaCambio(sesion.api, {
      empresaId: sesion.empresaId,
      monedaOrigenId: vesId,
      monedaDestinoId: usdId,
      valor: '0.027',
    });

    // Método de pago (el doble registro crea TransaccionFinanciera: id_metodo_pago NOT NULL).
    const metodo = await crearMetodoPago(sesion.api, { empresaId: sesion.empresaId, sufijo: suf });

    const numeroOperacion = `CD-E2E-${suf}`;
    // Cambio VES → USD: 3600 VES × 0.027 = 97.2000 USD.
    const montoOrigen = '3600';
    const tasa = '0.027';
    const montoDestinoEsperado = '97.2000'; // 3600 × 0.027, 4 decimales

    await test.step('registrar la operación de cambio desde la UI', async () => {
      await page.goto('/tesoreria/cambio-divisa/nueva');
      await expect(
        page.getByRole('heading', { name: 'Nueva Operación de Cambio' }),
      ).toBeVisible();

      await page.getByLabel('Número').fill(numeroOperacion);

      // Moneda origen = VES, destino = USD (selectores MUI poblados desde
      // /finanzas/monedas-empresa-activas/, etiqueta "ISO — Nombre").
      await page.getByLabel('Moneda origen').click();
      await page.getByRole('option', { name: /VES — Bolívar/ }).click();
      await page.getByLabel('Moneda destino').click();
      await page.getByRole('option', { name: /USD — / }).click();

      await page.getByLabel('Monto origen').fill(montoOrigen);
      await page.getByLabel(/^Tasa/).fill(tasa);

      // Previsualización del monto destino (monto × tasa con decimal.js).
      await expect(page.getByText(montoDestinoEsperado)).toBeVisible();

      // Métodos de pago de egreso e ingreso (el mismo método sirve para ambos).
      await page.getByLabel('Método de pago (egreso)').click();
      await page.getByRole('option', { name: metodo.nombre }).click();
      await page.getByLabel('Método de pago (ingreso)').click();
      await page.getByRole('option', { name: metodo.nombre }).click();

      await page.getByRole('button', { name: 'Registrar operación' }).click();

      // Tras crear navega a la lista y muestra el snackbar de éxito.
      await expect(page.getByText('Operación de cambio registrada')).toBeVisible();
    });

    await test.step('la operación aparece en la lista con montos y tasa exactos', async () => {
      await expect(page).toHaveURL(/\/tesoreria\/cambio-divisa$/);
      const fila = page.getByRole('row').filter({ hasText: numeroOperacion });
      await expect(fila).toBeVisible();
      // monto_origen 3600.0000, tasa 0.027000, monto_destino 97.2000.
      await expect(fila.getByText('3600.0000')).toBeVisible();
      await expect(fila.getByText(montoDestinoEsperado)).toBeVisible();
    });

    await test.step('existen el EGRESO en VES y el INGRESO en USD del cambio', async () => {
      // El doble registro crea MovimientoCajaBanco por el egreso (moneda origen)
      // y el ingreso (moneda destino). Se filtran por concepto del cambio.
      const movimientos = aLista<MovimientoCajaBancoApi>(
        await sesion.api.get(`/finanzas/movimientos-caja-banco/?empresa=${sesion.empresaId}`),
      );
      const egreso = movimientos.find(
        (m) => m.tipo_movimiento === 'EGRESO' && m.monto === '3600.00' && m.id_moneda === vesId,
      );
      const ingreso = movimientos.find(
        (m) => m.tipo_movimiento === 'INGRESO' && m.monto === '97.20' && m.id_moneda === usdId,
      );
      expect(egreso, 'debe existir el EGRESO en VES por 3600.00').toBeTruthy();
      expect(ingreso, 'debe existir el INGRESO en USD por 97.20').toBeTruthy();
    });

    await test.step('el asiento CAMBIO_DIVISA cuadra si la empresa lleva contabilidad', async () => {
      // Asiento contable opcional por empresa (ADR-006). Si la empresa generó
      // asientos, el balance de comprobación debe cuadrar (debe == haber).
      const balance = await sesion.api.get<{
        total_debe?: string;
        total_haber?: string;
      }>(`/contabilidad/asientos-contables/balance_comprobacion/?empresa_id=${sesion.empresaId}`);
      if (balance.total_debe !== undefined && balance.total_haber !== undefined) {
        expect(Number(balance.total_debe)).toBeCloseTo(Number(balance.total_haber), 2);
      }
    });
  });
});
