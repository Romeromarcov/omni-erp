import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';

/**
 * Flujo Notificaciones — centro de notificaciones del usuario (frontend e2e).
 *
 * El backend NO expone ningún endpoint para crear notificaciones (solo
 * `mis-notificaciones` y `marcar-leida`), así que NO se siembran datos: el flujo
 * realista es entrar a la pantalla, ver el encabezado y el estado (lista vacía o
 * con datos) y alternar el filtro "Solo no leídas". La sesión y la empresa
 * primaria las resuelve `iniciarSesion`.
 */
test.describe('Notificaciones: centro del usuario', () => {
  test('ve la bandeja y alterna el filtro de no leídas', async ({ page }) => {
    await iniciarSesion(page);

    await test.step('navegar al centro de notificaciones', async () => {
      await page.goto('/notificaciones');
      await expect(page.getByRole('heading', { name: 'Notificaciones' })).toBeVisible();
    });

    await test.step('la pantalla muestra un estado válido (vacío o con datos)', async () => {
      // Sin endpoint de siembra, la lista puede estar vacía: validamos que la
      // tabla renderice (encabezado de columna o mensaje de vacío).
      const vacio = page.getByText('Sin notificaciones');
      const columnaTitulo = page.getByRole('columnheader', { name: 'Título' });
      await expect(vacio.or(columnaTitulo).first()).toBeVisible();
    });

    await test.step('alternar el filtro "Solo no leídas"', async () => {
      const toggle = page.getByRole('switch', { name: 'Solo no leídas' });
      await expect(toggle).not.toBeChecked();
      await toggle.check();
      await expect(toggle).toBeChecked();

      // La pantalla sigue mostrando un estado válido tras filtrar.
      await expect(page.getByRole('heading', { name: 'Notificaciones' })).toBeVisible();

      await toggle.uncheck();
      await expect(toggle).not.toBeChecked();
    });
  });
});
