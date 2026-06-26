import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';

/**
 * Flujo Personalización (frontend e2e).
 *
 * Navega a la página de Personalización tras iniciar sesión y verifica el
 * encabezado, el panel de configuración activa (presente o con su estado vacío)
 * y la sección de historial de versiones. Simple y robusto: no depende de que la
 * empresa ya tenga versiones sembradas (backend operativo en /api/personalizacion/).
 */
test.describe('Personalización: versiones del DSL', () => {
  test('muestra la configuración activa y el historial', async ({ page }) => {
    await iniciarSesion(page);

    await page.goto('/personalizacion');

    await expect(page.getByRole('heading', { name: 'Personalización' })).toBeVisible();

    // El panel de configuración activa siempre se renderiza (con datos o vacío).
    await expect(page.getByText('Configuración activa')).toBeVisible();

    // La sección de historial siempre está presente.
    await expect(
      page.getByRole('heading', { name: 'Historial de versiones' }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Nueva versión' })).toBeVisible();
  });
});
