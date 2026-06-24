import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import {
  confirmarPedido,
  crearCatalogoInventario,
  crearCliente,
  crearPedido,
  sufijoUnico,
} from './helpers/datos';

/**
 * Flujo Despacho — logística de salida con máquina de estados (frontend e2e).
 *
 * Cadena: siembra catálogo + cliente + pedido vía API, confirma el pedido
 * (reserva stock + CxC), lo convierte a NotaVenta y la entrega (despacha stock,
 * deja la nota ENTREGADA). Con esa nota elegible, opera 100 % desde la UI de
 * Despachos: crea el despacho desde la nota de venta, inicia la ruta
 * (PENDIENTE → EN_RUTA) y registra la entrega (EN_RUTA → ENTREGADO).
 *
 * La sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Despacho: crear desde nota de venta → iniciar ruta → entregar', () => {
  test('opera el ciclo de despacho desde la UI', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const { api, empresaId } = sesion;
    const suf = sufijoUnico();

    const catalogo = await crearCatalogoInventario(api, empresaId, {
      stockInicial: '100',
      sufijo: suf,
    });
    const cliente = await crearCliente(api, empresaId, suf);
    const pedido = await crearPedido(api, {
      clienteId: cliente.clienteId,
      productoId: catalogo.productoId,
      cantidad: '5',
      precioUnitario: '100.00',
    });

    let numeroNota = '';
    await test.step('confirmar pedido, convertir a nota de venta y entregarla (API)', async () => {
      const confirmacion = await confirmarPedido(api, pedido.pedidoId, catalogo.almacenId);
      expect(confirmacion.estado).toBe('APROBADO');

      const nota = await api.post<{ id_nota_venta: string; numero_nota: string }>(
        `/ventas/pedidos/${pedido.pedidoId}/convertir-nota-venta/`,
        {},
      );
      // Entregar la nota deja stock despachado y la nota en ENTREGADA (elegible
      // para originar un despacho).
      await api.post(`/ventas/notas-venta/${nota.id_nota_venta}/entregar/`, {
        almacen_id: catalogo.almacenId,
      });
      numeroNota = nota.numero_nota;
    });

    await test.step('navegar a la página de Despachos', async () => {
      await page.goto('/despacho');
      await expect(page.getByRole('heading', { name: 'Despachos' })).toBeVisible();
    });

    await test.step('crear el despacho desde la nota de venta', async () => {
      await page.getByRole('button', { name: 'Crear desde nota de venta' }).click();
      await expect(
        page.getByRole('heading', { name: 'Crear despacho desde nota de venta' }),
      ).toBeVisible();

      // Selector de nota de venta (MUI): la nota recién entregada.
      await page.getByLabel(/Nota de venta/).click();
      await page.getByRole('option').filter({ hasText: numeroNota }).first().click();

      // Almacén de origen (MUI).
      await page.getByLabel(/Almacén de origen/).click();
      await page.getByRole('option', { name: catalogo.almacenNombre }).click();

      await page.getByLabel(/Dirección de entrega/).fill('Av. E2E 123, destino cliente');

      await page.getByRole('button', { name: 'Crear despacho' }).click();
      await expect(
        page.getByRole('heading', { name: 'Crear despacho desde nota de venta' }),
      ).toBeHidden();
    });

    await test.step('el despacho aparece pendiente', async () => {
      const fila = page.getByRole('row').filter({ hasText: 'Av. E2E 123' });
      await expect(fila).toBeVisible();
      await expect(fila.getByText('Pendiente')).toBeVisible();
    });

    await test.step('iniciar la ruta (PENDIENTE → EN_RUTA)', async () => {
      const fila = page.getByRole('row').filter({ hasText: 'Av. E2E 123' });
      page.once('dialog', (dialog) => dialog.accept());
      await fila.getByRole('button', { name: 'Iniciar ruta' }).click();
      await expect(
        page.getByRole('row').filter({ hasText: 'Av. E2E 123' }).getByText('En ruta'),
      ).toBeVisible();
    });

    await test.step('registrar la entrega (EN_RUTA → ENTREGADO)', async () => {
      const fila = page.getByRole('row').filter({ hasText: 'Av. E2E 123' });
      // El botón Entregar pide el receptor vía window.prompt: lo respondemos.
      page.once('dialog', (dialog) => dialog.accept('Receptor E2E'));
      await fila.getByRole('button', { name: 'Entregar' }).click();
      await expect(
        page.getByRole('row').filter({ hasText: 'Av. E2E 123' }).getByText('Entregado'),
      ).toBeVisible();
    });
  });
});
