import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Gestión de Aprobaciones (frontend e2e).
 *
 * Crea un Tipo de Aprobación 100 % vía UI desde la página de Configuración de
 * Aprobaciones y lo verifica en la lista. El backend ya está operativo (prefijo
 * /api/gestion-aprobaciones/); la sesión y la empresa primaria las resuelve
 * `iniciarSesion`. El tipo de aprobación solo requiere campos propios (código,
 * nombre, módulo), por lo que no depende de otros datos sembrados.
 */
test.describe('Gestión de Aprobaciones: configuración', () => {
  test('crea un tipo de aprobación desde la UI y lo ve en la lista', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const codigo = `APR${suf}`.slice(0, 20);
    const nombre = `Aprobación E2E ${suf}`;

    await test.step('navegar a Configuración de Aprobaciones', async () => {
      await page.goto('/aprobaciones/configuracion');
      await expect(
        page.getByRole('heading', { name: 'Configuración de Aprobaciones' }),
      ).toBeVisible();
    });

    await test.step('crear un tipo de aprobación nuevo', async () => {
      await page.getByRole('button', { name: 'Nuevo tipo' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo tipo de aprobación' })).toBeVisible();

      const dialog = page.getByRole('dialog');
      await dialog.getByLabel(/Código/).fill(codigo);
      await dialog.getByLabel(/Nombre/).fill(nombre);
      await dialog.getByLabel(/Módulo de origen/).fill('compras');

      await dialog.getByRole('button', { name: 'Guardar' }).click();
      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nuevo tipo de aprobación' })).toBeHidden();
    });

    await test.step('el tipo de aprobación aparece en la lista', async () => {
      await expect(page.getByText(nombre).first()).toBeVisible();
    });

    await test.step('ver el tab de Solicitudes', async () => {
      await page.goto('/aprobaciones/solicitudes');
      await expect(
        page.getByRole('heading', { name: 'Solicitudes de Aprobación' }),
      ).toBeVisible();
    });
  });
});
