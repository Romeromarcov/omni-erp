import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Nómina — Conceptos de Nómina (frontend e2e).
 *
 * Crea un concepto del catálogo de nómina 100 % vía UI desde /nomina/conceptos,
 * lo verifica en la lista y comprueba el filtro por tipo. El backend de nómina ya
 * está operativo (prefijo /api/nomina/); la sesión y la empresa primaria las
 * resuelve `iniciarSesion`.
 */
test.describe('Nómina: conceptos', () => {
  test('crea un concepto desde la UI, lo ve en la lista y filtra por tipo', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const codigo = `DEV-${suf}`.slice(0, 20);
    const nombre = `Bono E2E ${suf}`;

    await test.step('navegar a Conceptos de Nómina', async () => {
      await page.goto('/nomina/conceptos');
      await expect(page.getByRole('heading', { name: 'Conceptos de Nómina' })).toBeVisible();
    });

    await test.step('crear un concepto devengado', async () => {
      await page.getByRole('button', { name: 'Nuevo concepto' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo concepto' })).toBeVisible();

      await page.getByLabel(/Código/).fill(codigo);
      await page.getByLabel(/Nombre/).fill(nombre);
      await page.getByRole('button', { name: 'Guardar' }).click();

      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nuevo concepto' })).toBeHidden();
    });

    await test.step('el concepto aparece en la lista', async () => {
      const fila = page.getByRole('row').filter({ hasText: nombre });
      await expect(fila).toBeVisible();
      await expect(fila.getByText(codigo)).toBeVisible();
    });

    await test.step('filtra por tipo Devengado y sigue visible', async () => {
      await page.getByLabel('Tipo').click();
      await page.getByRole('option', { name: 'Devengado' }).click();
      await expect(page.getByRole('row').filter({ hasText: nombre })).toBeVisible();
    });
  });
});
