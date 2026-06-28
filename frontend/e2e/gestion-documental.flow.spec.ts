import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Gestión Documental — Carpetas y documentos (frontend e2e).
 *
 * Crea una carpeta 100 % vía UI desde la página de Documentos y verifica que
 * aparece en el panel de carpetas. La subida de archivos depende de S3/MinIO
 * (StorageService) que no siempre está disponible en CI; por eso el flujo
 * mínimo garantizado es crear carpeta + listar. El backend ya está operativo
 * (prefijo /api/gestion-documental/); la sesión la resuelve `iniciarSesion`.
 */
test.describe('Gestión Documental: carpetas y documentos', () => {
  test('crea una carpeta desde la UI y la ve en el panel', async ({ page }) => {
    await iniciarSesion(page);

    const suf = sufijoUnico();
    const nombreCarpeta = `Carpeta E2E ${suf}`;

    await test.step('navegar a la página de Documentos', async () => {
      await page.goto('/gestion-documental/documentos');
      await expect(page.getByRole('heading', { name: 'Documentos' })).toBeVisible();
    });

    await test.step('crear una carpeta nueva', async () => {
      await page.getByRole('button', { name: 'Nueva carpeta' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva carpeta' })).toBeVisible();

      await page.getByLabel('Nombre de la carpeta').fill(nombreCarpeta);
      await page.getByRole('button', { name: 'Guardar' }).click();

      // El diálogo se cierra al guardar correctamente.
      await expect(page.getByRole('heading', { name: 'Nueva carpeta' })).toBeHidden();
    });

    await test.step('la carpeta aparece en el panel de carpetas', async () => {
      // `exact: true`: el nombre también aparece en los aria-label de los botones
      // "Editar/Eliminar carpeta {nombre}" → sin exact matchearía 3 elementos.
      await expect(
        page.getByRole('button', { name: nombreCarpeta, exact: true }),
      ).toBeVisible();
    });

    await test.step('seleccionar la carpeta filtra la lista de documentos', async () => {
      await page.getByRole('button', { name: nombreCarpeta }).click();
      // Con la carpeta recién creada y vacía, la tabla muestra el estado vacío.
      await expect(page.getByText('Sin documentos. Sube el primero.')).toBeVisible();
    });
  });
});
