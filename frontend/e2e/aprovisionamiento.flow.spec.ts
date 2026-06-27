import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico, crearProducto } from './helpers/datos';

/**
 * Flujo Aprovisionamiento de Compras (source-to-PO) — frontend e2e.
 *
 * Crea una requisición de compra 100 % vía UI, la verifica en la tabla, abre el
 * drawer de líneas y agrega una línea para un producto sembrado. Luego navega a
 * las pestañas de Solicitudes de Cotización y Ofertas de Proveedor para verificar
 * que cargan. El backend (/api/compras/requisiciones-compra/, etc.) ya está
 * operativo; la sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Compras: aprovisionamiento (requisiciones → RFQ → ofertas)', () => {
  test('crea una requisición con una línea y navega por las pestañas', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    // El seed no crea productos: sembramos uno para la línea de la requisición.
    const { productoNombre } = await crearProducto(sesion.api, sesion.empresaId);

    const suf = sufijoUnico();
    const numero = `REQ-E2E-${suf}`.slice(0, 50);

    await test.step('navegar a Requisiciones', async () => {
      await page.goto('/compras/requisiciones');
      await expect(page.getByRole('heading', { name: 'Aprovisionamiento' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Requisiciones' })).toBeVisible();
    });

    await test.step('crear una requisición nueva', async () => {
      await page.getByRole('button', { name: 'Nueva requisición' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva requisición' })).toBeVisible();
      await page.getByLabel(/Número de requisición/).fill(numero);
      await page.getByLabel(/Justificación/).fill(`Reposición E2E ${suf}`);
      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva requisición' })).toBeHidden();
    });

    await test.step('la requisición aparece y se abre el drawer de líneas', async () => {
      const fila = page.getByRole('row').filter({ hasText: numero });
      await expect(fila).toBeVisible();
      await fila.getByRole('button', { name: 'Líneas' }).click();
      await expect(page.getByText('Líneas de la requisición')).toBeVisible();
    });

    await test.step('agregar una línea para el producto sembrado', async () => {
      await page.getByLabel(/Producto/).click();
      // El name del option es substring-match: basta el nombre del producto.
      await page.getByRole('option', { name: productoNombre }).click();
      await page.getByLabel('Cantidad', { exact: true }).fill('7');
      await page.getByRole('button', { name: 'Agregar línea' }).click();
      // La línea aparece listada en el drawer (producto · cantidad 7).
      await expect(page.getByText(productoNombre, { exact: false })).toBeVisible();
    });

    await test.step('cerrar el drawer y navegar a Solicitudes de Cotización', async () => {
      await page.getByRole('button', { name: 'Cerrar detalle' }).click();
      await page.getByRole('tab', { name: 'Solicitudes de Cotización' }).click();
      await expect(page.getByRole('button', { name: 'Nueva solicitud' })).toBeVisible();
    });

    await test.step('navegar a Ofertas de Proveedor', async () => {
      await page.getByRole('tab', { name: 'Ofertas de Proveedor' }).click();
      await expect(page.getByRole('button', { name: 'Nueva oferta' })).toBeVisible();
    });
  });
});
