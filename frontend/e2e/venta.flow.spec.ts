import { test, expect } from '@playwright/test';
import { formatoMonedaDashboard, iniciarSesion } from './helpers/sesion';
import {
  carteraDashboard,
  confirmarPedido,
  crearCatalogoInventario,
  crearCliente,
  crearPedido,
  sufijoUnico,
} from './helpers/datos';

/**
 * Flujo crítico 1 — Venta (TEST-6 / Fase 4).
 *
 * Cadena soportada HOY por el producto: pedido → confirmar (reserva stock +
 * genera CxC). La confirmación se dispara vía API porque la UI actual no tiene
 * botón "Confirmar" en el detalle del pedido, y los botones "Convertir a
 * factura/nota" del frontend llaman endpoints (`convertir-*`) que NO existen en
 * el backend (gap documentado en el PR). La verificación de stock reservado y
 * de la CxC generada sí se hace contra la UI real.
 */
test.describe('Venta: pedido → confirmación → stock y CxC', () => {
  test('crea un pedido, lo confirma y verifica stock comprometido y CxC en la UI', async ({
    page,
  }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();

    const catalogo = await crearCatalogoInventario(sesion.api, sesion.empresaId, {
      stockInicial: '100',
      sufijo: suf,
    });
    const cliente = await crearCliente(sesion.api, sesion.empresaId, suf);
    const pedido = await crearPedido(sesion.api, {
      clienteId: cliente.clienteId,
      productoId: catalogo.productoId,
      cantidad: '5',
      precioUnitario: '100.00',
    });

    await test.step('el pedido aparece en el listado y su detalle es correcto', async () => {
      await page.goto('/ventas/pedidos');
      const fila = page.getByRole('row').filter({ hasText: pedido.numeroPedido });
      await expect(fila).toBeVisible();
      await fila.click();

      await expect(
        page.getByRole('heading', { name: `Pedido ${pedido.numeroPedido}` }),
      ).toBeVisible();
      await expect(page.getByText('PENDIENTE')).toBeVisible();
      await expect(page.getByText(catalogo.productoNombre)).toBeVisible();
      await expect(page.getByText(cliente.razonSocial)).toBeVisible();
    });

    let cxcId: string | null = null;
    await test.step('confirmar el pedido (API) reserva stock y genera la CxC', async () => {
      const confirmacion = await confirmarPedido(sesion.api, pedido.pedidoId, catalogo.almacenId);
      expect(confirmacion.estado).toBe('APROBADO');
      expect(confirmacion.cxc_generada).toBe(true);
      expect(confirmacion.reservas_creadas).toBeGreaterThan(0);
      cxcId = confirmacion.cxc_id;
    });

    await test.step('la UI refleja el pedido APROBADO', async () => {
      await page.reload();
      await expect(page.getByText('APROBADO')).toBeVisible();
    });

    await test.step('el stock del producto muestra la cantidad comprometida', async () => {
      await page.goto('/inventario/stock');
      await page.getByPlaceholder('Buscar producto…').fill(catalogo.productoNombre);
      const fila = page.getByRole('row').filter({ hasText: catalogo.productoNombre });
      await expect(fila).toBeVisible();
      // Disponible 100 (la reserva compromete, no descuenta) y Comprometido 5.
      await expect(fila.getByRole('cell', { name: '100', exact: true })).toBeVisible();
      await expect(fila.getByRole('cell', { name: '5', exact: true })).toBeVisible();
    });

    await test.step('la CxC generada existe y el dashboard de cartera la refleja', async () => {
      const cxc = await sesion.api.get<{ saldo_pendiente: string; referencia_externa: string }>(
        `/cxc/cuentas-por-cobrar/${cxcId}/`,
      );
      expect(cxc.saldo_pendiente).toBe('500.00');
      expect(cxc.referencia_externa).toBe(pedido.numeroPedido);

      // El dashboard agrega toda la cartera y el backend la CACHEA 15 min
      // (gap documentado en el PR: el aging no se invalida al crear CxC/abonar),
      // así que la verificación de UI es de consistencia con la misma API que
      // consume la página, no de valor absoluto.
      const cartera = await carteraDashboard(sesion.api);
      await page.goto('/cobranza/dashboard');
      await expect(page.getByText('Total Pendiente')).toBeVisible();
      await expect(
        page.getByText(formatoMonedaDashboard(cartera.total_pendiente)).first(),
      ).toBeVisible();
    });
  });
});
