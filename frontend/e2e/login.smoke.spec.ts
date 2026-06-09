import { test, expect } from '@playwright/test';

/**
 * Smoke E2E (TEST-6) — el flujo más simple: cargar la pantalla de login y
 * comprobar que el formulario se renderiza y es usable.
 *
 * Requiere el frontend vivo (dev server o build servido) en `E2E_BASE_URL`.
 * No depende del backend: solo valida el render de la pantalla de entrada.
 */
test.describe('Login — smoke', () => {
  test('renderiza el formulario de inicio de sesión', async ({ page }) => {
    await page.goto('/login');

    // Título de la pantalla. La pantalla de login muestra el texto "Iniciar
    // sesión" en dos headings (el título de página `h6` de LoginPage y el `h2`
    // propio de LoginForm), por lo que el rol "heading" resuelve a 2 elementos;
    // `.first()` evita el strict-mode violation y basta para el smoke (confirmar
    // que el título se renderiza).
    await expect(
      page.getByRole('heading', { name: /iniciar sesión/i }).first(),
    ).toBeVisible();

    // Campos de credenciales y botón de envío.
    await expect(page.getByLabel(/usuario/i)).toBeVisible();
    await expect(page.getByLabel(/contraseña/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /ingresar/i })).toBeVisible();
  });

  test('permite escribir credenciales en los campos', async ({ page }) => {
    await page.goto('/login');

    const usuario = page.getByLabel(/usuario/i);
    await usuario.fill('demo');
    await expect(usuario).toHaveValue('demo');
  });
});
