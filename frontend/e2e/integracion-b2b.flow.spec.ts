import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Integración B2B (frontend e2e).
 *
 * Crea una configuración de integración 100 % vía UI desde la página de
 * Integración B2B y la verifica en la lista. El backend ya está operativo
 * (prefijo /api/integracion-b2b/); la sesión y la empresa primaria las resuelve
 * `iniciarSesion`.
 */
test.describe('Integración B2B: configuraciones', () => {
  test('crea una configuración desde la UI y la ve en la lista', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const nombre = `Integración B2B E2E ${suf}`;

    await test.step('navegar a la página de Integración B2B', async () => {
      await page.goto('/integracion-b2b');
      await expect(page.getByRole('heading', { name: 'Integración B2B' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Configuraciones' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Mapeo de campos' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Logs' })).toBeVisible();
    });

    await test.step('crear una configuración nueva', async () => {
      await page.getByRole('button', { name: 'Nueva configuración' }).click();
      await expect(
        page.getByRole('heading', { name: 'Nueva configuración' }),
      ).toBeVisible();

      await page.getByLabel(/Nombre de la integración/).fill(nombre);
      await page.getByLabel(/Tipo de integración/).fill('REST');
      await page.getByRole('button', { name: 'Guardar' }).click();

      // El diálogo se cierra al guardar correctamente.
      await expect(
        page.getByRole('heading', { name: 'Nueva configuración' }),
      ).toBeHidden();
    });

    await test.step('la configuración aparece en la lista', async () => {
      const fila = page.getByRole('row').filter({ hasText: nombre });
      await expect(fila).toBeVisible();
      await expect(fila.getByText('REST')).toBeVisible();
    });
  });
});
