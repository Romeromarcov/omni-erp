import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Proveedores — Maestro de Proveedores (frontend e2e).
 *
 * Crea un proveedor 100 % vía UI desde la página de Proveedores, lo verifica en
 * la lista, lo edita y confirma el cambio. El backend de proveedores ya está
 * operativo (prefijo /api/proveedores/); la sesión y la empresa primaria las
 * resuelve `iniciarSesion`.
 */
test.describe('Proveedores: maestro de proveedores', () => {
  test('crea un proveedor desde la UI, lo ve en la lista y lo edita', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const razonSocial = `Proveedor E2E ${suf}`;
    const razonSocialEditada = `${razonSocial} (editado)`;
    // RIF venezolano válido: letra + guion + dígitos (validador del backend).
    const rif = `J-${String(Date.now()).slice(-8)}`;

    await test.step('navegar a la página de Proveedores', async () => {
      await page.goto('/proveedores/proveedores');
      await expect(page.getByRole('heading', { name: 'Proveedores' })).toBeVisible();
    });

    await test.step('crear un proveedor nuevo', async () => {
      await page.getByRole('button', { name: 'Nuevo proveedor' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo proveedor' })).toBeVisible();

      await page.getByLabel(/Razón social/).fill(razonSocial);
      await page.getByLabel(/RIF/).fill(rif);
      await page.getByRole('button', { name: 'Guardar' }).click();

      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nuevo proveedor' })).toBeHidden();
    });

    await test.step('el proveedor aparece en la lista', async () => {
      await page.getByLabel('Buscar').fill(razonSocial);
      const fila = page.getByRole('row').filter({ hasText: razonSocial });
      await expect(fila).toBeVisible();
      await expect(fila.getByText(rif)).toBeVisible();
    });

    await test.step('editar la razón social del proveedor', async () => {
      const fila = page.getByRole('row').filter({ hasText: razonSocial });
      await fila.getByRole('button', { name: 'Editar' }).click();
      await expect(page.getByRole('heading', { name: 'Editar proveedor' })).toBeVisible();

      await page.getByLabel(/Razón social/).fill(razonSocialEditada);
      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Editar proveedor' })).toBeHidden();

      await page.getByLabel('Buscar').fill(razonSocialEditada);
      await expect(
        page.getByRole('row').filter({ hasText: razonSocialEditada }),
      ).toBeVisible();
    });
  });
});
