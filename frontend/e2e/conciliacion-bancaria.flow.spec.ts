import { test, expect } from '@playwright/test';
import { iniciarSesion, aLista } from './helpers/sesion';
import {
  sufijoUnico,
  monedaUsd,
  crearCuentaBancaria,
  crearMetodoPago,
  crearPagoIngresoBancario,
  crearMovimientoBancario,
} from './helpers/datos';

/**
 * Flujo crítico — Conciliación Bancaria (tesorería ↔ finanzas).
 *
 * Cadena de punta a punta soportada HOY por el producto, manejada vía UI:
 *   abrir una sesión de conciliación por cuenta/período → ejecutar la
 *   conciliación automática (empareja MovimientoBancario CREDITO con un Pago
 *   INGRESO de la misma cuenta por monto+fecha) → cerrar la sesión.
 *
 * Cruza tesoreria (MovimientoBancario / ConciliacionBancaria) → finanzas
 * (CuentaBancariaEmpresa / Pago).
 *
 * Prerequisitos sembrados vía API:
 *   - una cuenta bancaria USD;
 *   - un Pago INGRESO atado a esa cuenta (contraparte interna del extracto);
 *   - un MovimientoBancario CREDITO del mismo monto/cuenta/fecha (línea del
 *     extracto que debe conciliarse contra el pago).
 *
 * Efectos verificados:
 *   - UI: la conciliación nace ABIERTA; tras "Conciliar automático" el
 *     movimiento del extracto pasa a CONCILIADO; tras "Cerrar" la sesión queda
 *     CERRADA;
 *   - API: el MovimientoBancario quedó CONCILIADO con id_pago_conciliado, y la
 *     ConciliacionBancaria quedó CERRADA.
 */

interface MovimientoBancarioApi {
  id: string;
  estado: string;
  id_pago_conciliado: string | null;
}

interface ConciliacionApi {
  id: string;
  estado: string;
}

test.describe('Conciliación bancaria: sesión → conciliar-auto → cerrar', () => {
  test('concilia un movimiento contra un pago por UI y cierra la sesión', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();
    const hoy = new Date().toISOString().slice(0, 10);

    // ── Prerequisitos sembrados vía API ──────────────────────────────────────
    const usdId = await monedaUsd(sesion.api);
    const cuenta = await crearCuentaBancaria(sesion.api, {
      empresaId: sesion.empresaId,
      monedaId: usdId,
      nombreBanco: `Banco Conci ${suf}`,
      sufijo: suf,
    });
    const metodo = await crearMetodoPago(sesion.api, { empresaId: sesion.empresaId, sufijo: suf });

    const monto = '1500.00';
    const referencia = `REF-CONCI-${suf}`;

    // Pago INGRESO (contraparte interna) y movimiento del extracto, mismo
    // monto/cuenta/fecha/referencia → la conciliación automática los empareja.
    await crearPagoIngresoBancario(sesion.api, {
      empresaId: sesion.empresaId,
      cuentaBancariaId: cuenta.cuentaId,
      monedaId: usdId,
      metodoPagoId: metodo.metodoId,
      monto,
      referencia,
      fecha: hoy,
    });
    const movimiento = await crearMovimientoBancario(sesion.api, {
      empresaId: sesion.empresaId,
      cuentaBancariaId: cuenta.cuentaId,
      descripcion: `Abono cliente ${suf}`,
      monto,
      referencia,
      fecha: hoy,
      tipo: 'CREDITO',
    });

    let conciliacionId = '';

    await test.step('abrir una sesión de conciliación desde la UI', async () => {
      await page.goto('/tesoreria/conciliaciones');
      await expect(page.getByRole('heading', { name: 'Conciliación Bancaria' })).toBeVisible();

      await page.getByRole('button', { name: 'Nueva conciliación' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      await dialogo.getByLabel('Cuenta bancaria').click();
      // La opción se etiqueta "{nombre_banco} — {numero_cuenta}"; el número es único.
      await page.getByRole('option').filter({ hasText: cuenta.numeroCuenta }).click();
      // El período cubre hoy (defaults del formulario = hoy → hoy).
      await dialogo.getByLabel('Saldo banco').fill('1500.00');
      await dialogo.getByLabel('Saldo libros').fill('1500.00');
      await dialogo.getByRole('button', { name: 'Guardar' }).click();

      await expect(page.getByText('Conciliación creada')).toBeVisible();
      // Tras crear navega al detalle: /tesoreria/conciliaciones/{id}.
      await expect(page).toHaveURL(/\/tesoreria\/conciliaciones\/[0-9a-f-]+$/);
      await expect(page.getByRole('heading', { name: 'Detalle de Conciliación' })).toBeVisible();
      conciliacionId = page.url().split('/').pop() ?? '';
      expect(conciliacionId).not.toBe('');

      // El movimiento del extracto aparece PENDIENTE.
      const fila = page.getByRole('row').filter({ hasText: `Abono cliente ${suf}` });
      await expect(fila).toBeVisible();
      await expect(fila.getByText('PENDIENTE')).toBeVisible();
    });

    await test.step('conciliar automático empareja el movimiento con el pago', async () => {
      await page.getByRole('button', { name: 'Conciliar automático' }).click();
      await expect(page.getByText(/Conciliados 1 movimientos/)).toBeVisible();

      // El movimiento pasa a CONCILIADO en la tabla del detalle.
      const fila = page.getByRole('row').filter({ hasText: `Abono cliente ${suf}` });
      await expect(fila.getByText('CONCILIADO')).toBeVisible();
    });

    await test.step('cerrar la sesión de conciliación', async () => {
      await page.getByRole('button', { name: 'Cerrar conciliación' }).click();
      await expect(page.getByText('Conciliación cerrada')).toBeVisible();
      // Tras cerrar desaparecen las acciones de conciliar/cerrar (sólo en ABIERTA).
      await expect(page.getByRole('button', { name: 'Cerrar conciliación' })).toHaveCount(0);
    });

    await test.step('verificación por API: movimiento CONCILIADO y sesión CERRADA', async () => {
      const movimientos = aLista<MovimientoBancarioApi>(
        await sesion.api.get(
          `/tesoreria/movimientos-bancarios/?cuenta=${cuenta.cuentaId}&estado=CONCILIADO`,
        ),
      );
      const conciliado = movimientos.find((m) => m.id === movimiento.id);
      expect(conciliado, 'el movimiento del extracto debe quedar CONCILIADO').toBeTruthy();
      expect(conciliado!.estado).toBe('CONCILIADO');
      expect(conciliado!.id_pago_conciliado, 'debe quedar atado al pago interno').toBeTruthy();

      const conciliacion = await sesion.api.get<ConciliacionApi>(
        `/tesoreria/conciliaciones-bancarias/${conciliacionId}/`,
      );
      expect(conciliacion.estado).toBe('CERRADA');
    });
  });
});
