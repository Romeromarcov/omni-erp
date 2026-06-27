import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo RRHH — Beneficios y Licencias (frontend e2e).
 *
 * Crea un beneficio 100 % vía UI desde la pestaña Beneficios, lo verifica en la
 * tabla y luego navega a la pestaña Licencias. El backend de RRHH ya está
 * operativo (prefijo /api/rrhh/); la sesión y la empresa primaria las resuelve
 * `iniciarSesion`.
 */
test.describe('RRHH: beneficios y licencias', () => {
  test('crea un beneficio desde la UI, lo ve en la lista y navega a licencias', async ({
    page,
  }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const nombreBeneficio = `Beneficio E2E ${suf}`;

    await test.step('navegar a Beneficios y Licencias', async () => {
      await page.goto('/rrhh/beneficios');
      await expect(page.getByRole('heading', { name: 'Beneficios y Licencias' })).toBeVisible();
    });

    await test.step('crear un beneficio nuevo', async () => {
      await page.getByRole('button', { name: 'Nuevo beneficio' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo beneficio' })).toBeVisible();

      await page.getByLabel(/Nombre del beneficio/).fill(nombreBeneficio);
      await page.getByRole('button', { name: 'Guardar' }).click();

      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nuevo beneficio' })).toBeHidden();
    });

    await test.step('el beneficio aparece en la lista', async () => {
      const fila = page.getByRole('row').filter({ hasText: nombreBeneficio });
      await expect(fila).toBeVisible();
    });

    await test.step('navegar a la pestaña Licencias', async () => {
      await page.getByRole('tab', { name: 'Licencias' }).click();
      await expect(page.getByRole('button', { name: 'Nueva licencia' })).toBeVisible();
    });
  });
});
