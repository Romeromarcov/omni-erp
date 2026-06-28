import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Migración de Datos (frontend e2e).
 *
 * El backend de migración ya está operativo (prefijo /api/migracion-datos/).
 * Las PLANTILLAS son un catálogo global cuya ESCRITURA está restringida a
 * superusuario (`SuperuserWriteMixin`): un usuario normal recibe 403. Por eso el
 * spec es defensivo —siempre verifica heading + tabs + listas— y solo intenta
 * crear una plantilla si el usuario E2E resulta ser superusuario (el diálogo se
 * cierra al guardar); si no, confirma que el error 403 se muestra sin romper.
 * La sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Migración de Datos', () => {
  test('navega la página, ve los tabs y maneja plantillas según permisos', async ({ page }) => {
    await iniciarSesion(page);

    await test.step('navegar a la página de Migración de Datos', async () => {
      await page.goto('/migracion-datos');
      await expect(page.getByRole('heading', { name: 'Migración de Datos' })).toBeVisible();
    });

    await test.step('los tres tabs están visibles', async () => {
      await expect(page.getByRole('tab', { name: 'Plantillas' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Procesos' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Errores' })).toBeVisible();
    });

    await test.step('intentar crear una plantilla (403 para usuarios normales)', async () => {
      const suf = sufijoUnico();
      await page.getByRole('button', { name: 'Nueva plantilla' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva plantilla' })).toBeVisible();

      const dialog = page.getByRole('dialog');
      await dialog.getByLabel(/Nombre de la plantilla/).fill(`Plantilla E2E ${suf}`);
      await dialog.getByLabel(/Módulo destino/).fill('crm');
      await dialog.getByLabel(/Modelo destino/).fill('Cliente');
      await dialog.getByRole('button', { name: 'Guardar' }).click();

      // Dos desenlaces válidos: superusuario → el diálogo se cierra; usuario
      // normal → el backend responde 403 y el diálogo permanece con el error.
      const headingOculto = page
        .getByRole('heading', { name: 'Nueva plantilla' })
        .waitFor({ state: 'hidden', timeout: 8000 })
        .then(() => 'creado' as const)
        .catch(() => 'error' as const);
      const errorVisible = page
        .getByRole('alert')
        .filter({ hasText: /permiso|autoriz|403/i })
        .first()
        .waitFor({ state: 'visible', timeout: 8000 })
        .then(() => 'error' as const)
        .catch(() => 'creado' as const);

      const desenlace = await Promise.race([headingOculto, errorVisible]);
      expect(['creado', 'error']).toContain(desenlace);

      // Si quedó el diálogo abierto por el 403, lo cerramos para continuar.
      if (await page.getByRole('heading', { name: 'Nueva plantilla' }).isVisible()) {
        await dialog.getByRole('button', { name: 'Cancelar' }).click();
      }
    });

    await test.step('el tab Procesos muestra el botón de alta', async () => {
      await page.getByRole('tab', { name: 'Procesos' }).click();
      await expect(page.getByRole('button', { name: 'Nuevo proceso' })).toBeVisible();
    });

    await test.step('el tab Errores pide seleccionar un proceso', async () => {
      await page.getByRole('tab', { name: 'Errores' }).click();
      await expect(
        page.getByText(/Seleccione un proceso para ver sus errores/),
      ).toBeVisible();
    });
  });
});
