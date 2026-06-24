import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';

/**
 * Flujo Agentes IA — gestión de predicciones/sugerencias (frontend e2e).
 *
 * El backend no expone un endpoint de siembra de predicciones, así que NO se
 * siembran datos: el flujo realista es entrar a la pantalla, ver el encabezado
 * y un estado válido (lista vacía o con datos) y ejercitar los filtros por
 * agente y por resultado. La sesión y la empresa primaria las resuelve
 * `iniciarSesion`.
 */
test.describe('Agentes IA: predicciones y análisis', () => {
  test('ve la pantalla, el estado de la lista y aplica filtros', async ({ page }) => {
    await iniciarSesion(page);

    await test.step('navegar a la página de Agentes IA', async () => {
      await page.goto('/agentes');
      await expect(page.getByRole('heading', { name: 'Agentes IA' })).toBeVisible();
    });

    await test.step('la pantalla muestra un estado válido (vacío o con datos)', async () => {
      const vacio = page.getByText('Sin predicciones registradas todavía.');
      const columnaAgente = page.getByRole('columnheader', { name: 'Agente' });
      await expect(vacio.or(columnaAgente).first()).toBeVisible();
      // El panel de análisis y la sección de métricas siempre están presentes.
      await expect(page.getByRole('heading', { name: 'Disparar análisis' })).toBeVisible();
      await expect(
        page.getByRole('heading', { name: 'Métricas del clasificador de gastos' }),
      ).toBeVisible();
    });

    await test.step('filtrar por agente', async () => {
      await page.getByLabel('Agente').click();
      await page.getByRole('option', { name: 'Estratega de Cobranza' }).click();
      await expect(page.getByRole('heading', { name: 'Agentes IA' })).toBeVisible();
    });

    await test.step('filtrar por resultado', async () => {
      await page.getByLabel('Resultado').click();
      await page.getByRole('option', { name: 'Pendiente' }).click();
      await expect(page.getByRole('heading', { name: 'Agentes IA' })).toBeVisible();
    });
  });
});
