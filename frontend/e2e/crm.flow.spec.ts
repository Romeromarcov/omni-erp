import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo CRM — Maestro de Clientes (frontend e2e).
 *
 * Crea un cliente 100 % vía UI desde la página de Clientes, lo verifica en la
 * lista, lo edita y confirma el cambio. El backend de CRM ya está operativo
 * (prefijo /api/crm/); la sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('CRM: maestro de clientes', () => {
  test('crea un cliente desde la UI, lo ve en la lista y lo edita', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const razonSocial = `Cliente CRM E2E ${suf}`;
    const razonSocialEditada = `${razonSocial} (editado)`;
    // RIF venezolano válido: letra + guion + dígitos (validador del backend).
    const rif = `J-${String(Date.now()).slice(-8)}`;

    await test.step('navegar a la página de Clientes', async () => {
      await page.goto('/crm/clientes');
      await expect(page.getByRole('heading', { name: 'Clientes' })).toBeVisible();
    });

    await test.step('crear un cliente nuevo', async () => {
      await page.getByRole('button', { name: 'Nuevo cliente' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo cliente' })).toBeVisible();

      await page.getByLabel(/Razón social/).fill(razonSocial);
      await page.getByLabel(/RIF/).fill(rif);
      await page.getByRole('button', { name: 'Guardar' }).click();

      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nuevo cliente' })).toBeHidden();
    });

    await test.step('el cliente aparece en la lista', async () => {
      await page.getByLabel('Buscar').fill(razonSocial);
      const fila = page.getByRole('row').filter({ hasText: razonSocial });
      await expect(fila).toBeVisible();
      await expect(fila.getByText(rif)).toBeVisible();
    });

    await test.step('editar la razón social del cliente', async () => {
      const fila = page.getByRole('row').filter({ hasText: razonSocial });
      await fila.getByRole('button', { name: 'Editar' }).click();
      await expect(page.getByRole('heading', { name: 'Editar cliente' })).toBeVisible();

      await page.getByLabel(/Razón social/).fill(razonSocialEditada);
      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Editar cliente' })).toBeHidden();

      await page.getByLabel('Buscar').fill(razonSocialEditada);
      await expect(
        page.getByRole('row').filter({ hasText: razonSocialEditada }),
      ).toBeVisible();
    });
  });
});
