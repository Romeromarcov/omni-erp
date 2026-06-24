import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Gastos — registro + workflow de aprobación (frontend e2e).
 *
 * Siembra una categoría de gasto vía API (prefijo /api/gastos/), registra un
 * gasto 100 % desde la UI de la página de Gastos, lo aprueba con su confirmación
 * y verifica que la fila pasa a estado "Aprobado". La aprobación genera el
 * asiento contable cuando la empresa exige contabilidad; con la empresa de seed
 * (sin contabilidad obligatoria) la transición a APROBADO se completa igual.
 *
 * La sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Gastos: registro y aprobación', () => {
  test('registra un gasto desde la UI y lo aprueba', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const { api, empresaId } = sesion;

    const suf = sufijoUnico();
    const descripcion = `Gasto E2E ${suf}`;
    const categoriaNombre = `Categoría Gasto E2E ${suf}`;

    // Sembramos la categoría vía API: la UI de Gastos la necesita en su selector
    // (carga las categorías activas del tenant). `requiere_factura=false` para
    // que el gasto sin factura se pueda aprobar.
    await test.step('sembrar categoría de gasto', async () => {
      await api.post('/gastos/categorias-gasto/', {
        id_empresa: empresaId,
        nombre_categoria: categoriaNombre,
        requiere_factura: false,
        activo: true,
      });
    });

    await test.step('navegar a la página de Gastos', async () => {
      await page.goto('/gastos');
      await expect(page.getByRole('heading', { name: 'Gastos' })).toBeVisible();
    });

    await test.step('registrar un gasto nuevo', async () => {
      await page.getByRole('button', { name: 'Nuevo gasto' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo gasto' })).toBeVisible();

      // Categoría (selector MUI).
      await page.getByLabel(/Categoría/).click();
      await page.getByRole('option', { name: categoriaNombre }).click();

      await page.getByLabel(/Descripción/).fill(descripcion);
      await page.getByLabel(/^Monto/).fill('150.00');

      // Moneda (selector MUI): USD del seed.
      await page.getByLabel(/Moneda/).click();
      await page.getByRole('option').filter({ hasText: 'USD' }).first().click();

      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo gasto' })).toBeHidden();
    });

    await test.step('el gasto aparece pendiente de aprobación', async () => {
      const fila = page.getByRole('row').filter({ hasText: descripcion });
      await expect(fila).toBeVisible();
      await expect(fila.getByText(/Pendiente/)).toBeVisible();
    });

    await test.step('aprobar el gasto', async () => {
      const fila = page.getByRole('row').filter({ hasText: descripcion });
      // El botón Aprobar dispara un window.confirm: lo auto-aceptamos.
      page.once('dialog', (dialog) => dialog.accept());
      await fila.getByRole('button', { name: 'Aprobar' }).click();

      await expect(
        page.getByRole('row').filter({ hasText: descripcion }).getByText(/Aprobado/),
      ).toBeVisible();
    });
  });
});
