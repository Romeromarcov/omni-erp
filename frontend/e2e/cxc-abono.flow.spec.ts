import { test, expect } from '@playwright/test';
import { formatoMonedaDashboard, iniciarSesion } from './helpers/sesion';
import {
  abonarCuentaPorCobrar,
  carteraDashboard,
  crearCliente,
  crearCuentaPorCobrar,
} from './helpers/datos';

/**
 * Flujo crítico 2 — Cobro/abono de CxC (TEST-6 / Fase 4).
 *
 * Gaps reales documentados en el PR:
 *   - La UI de cobranza no tiene formulario de abono (las páginas CxC son
 *     dashboard/gestiones/acuerdos), por lo que el abono se registra vía la
 *     API real (`POST /cxc/cuentas-por-cobrar/{id}/abonar/`).
 *   - El backend CACHEA el aging de cartera 15 min sin invalidarlo al abonar,
 *     así que el dashboard puede mostrar un total desactualizado. La
 *     verificación de UI es de consistencia: el dashboard muestra exactamente
 *     lo que reporta la API que consume.
 */
test.describe('CxC: abono y saldo actualizado', () => {
  test('registra un abono y el saldo de la CxC se actualiza', async ({ page }) => {
    const sesion = await iniciarSesion(page);

    const cliente = await crearCliente(sesion.api, sesion.empresaId);
    const cxc = await crearCuentaPorCobrar(sesion.api, {
      empresaId: sesion.empresaId,
      clienteId: cliente.clienteId,
      monto: '350.00',
      descripcion: 'CxC E2E para abono',
    });
    expect(cxc.saldo_pendiente).toBe('350.00');

    await test.step('registrar un abono parcial deja la CxC en estado parcial', async () => {
      const abono = await abonarCuentaPorCobrar(sesion.api, cxc.id, '150.00');
      expect(abono.estado_cxc).toBe('parcial');
      expect(abono.monto_abonado).toBe('150.00');
    });

    await test.step('el saldo pendiente queda actualizado (350 - 150 = 200)', async () => {
      const actualizada = await sesion.api.get<{ saldo_pendiente: string; estado: string }>(
        `/cxc/cuentas-por-cobrar/${cxc.id}/`,
      );
      expect(actualizada.saldo_pendiente).toBe('200.00');
      expect(actualizada.estado).toBe('parcial');
    });

    await test.step('el dashboard de cartera muestra el total que reporta la API', async () => {
      const cartera = await carteraDashboard(sesion.api);
      await page.goto('/cobranza/dashboard');
      await expect(page.getByText('Total Pendiente')).toBeVisible();
      await expect(
        page.getByText(formatoMonedaDashboard(cartera.total_pendiente)).first(),
      ).toBeVisible();
    });
  });
});
