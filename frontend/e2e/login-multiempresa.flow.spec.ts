import { test, expect } from '@playwright/test';
import { credencialesE2E } from './helpers/sesion';

/**
 * Flujo crítico 5 — Login + navegación multi-empresa (TEST-6 / Fase 4).
 *
 * Login 100 % vía UI con las credenciales del seed (`seed_empresa_inicial`
 * corre dos veces y asocia ambas empresas al mismo admin), selección de
 * empresa/sucursal y navegación por módulos en el contexto elegido.
 */
test.describe('Login y navegación multi-empresa', () => {
  test('inicia sesión, elige empresa/sucursal y navega módulos', async ({ page }) => {
    const { usuario, password } = credencialesE2E();

    await test.step('login con credenciales válidas', async () => {
      await page.goto('/login');
      await page.getByLabel(/usuario/i).fill(usuario);
      await page.getByLabel(/contraseña/i).fill(password);
      await page.getByRole('button', { name: /ingresar/i }).click();
    });

    await test.step('el selector ofrece las dos empresas del seed', async () => {
      await expect(page.getByText('Selecciona empresa y sucursal')).toBeVisible();
      // Los Select de MUI no exponen nombre accesible aquí: el primero es
      // Empresa y el segundo (deshabilitado hasta elegir empresa) es Sucursal.
      await page.getByRole('combobox').first().click();
      await expect(
        page.getByRole('option', { name: 'Empresa E2E Uno C.A.' }),
      ).toBeVisible();
      await expect(
        page.getByRole('option', { name: 'Empresa E2E Dos C.A.' }),
      ).toBeVisible();
      await page.getByRole('option', { name: 'Empresa E2E Uno C.A.' }).click();

      await page.getByRole('combobox').nth(1).click();
      await page.getByRole('option', { name: 'Principal' }).click();
      await page.getByRole('button', { name: 'Continuar' }).click();
    });

    await test.step('aterriza en el dashboard con el contexto elegido', async () => {
      await expect(page).toHaveURL(/\/dashboard$/);
      await expect(page.getByText(/Bienvenido/)).toBeVisible();
      await expect(page.getByText(/· Principal/)).toBeVisible();
    });

    await test.step('navega a módulos clave ya autenticado', async () => {
      await page.goto('/inventario/stock');
      await expect(page.getByRole('heading', { name: 'Stock Actual' })).toBeVisible();

      await page.goto('/cobranza/dashboard');
      await expect(
        page.getByRole('heading', { name: 'Dashboard de Cartera' }),
      ).toBeVisible();
    });
  });
});
