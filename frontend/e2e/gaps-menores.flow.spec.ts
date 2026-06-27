import { test, expect } from '@playwright/test';
import { iniciarSesion, type ApiE2E } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo "gaps menores" — Ubicaciones de Almacén (frontend e2e).
 *
 * Cubre una de las cuatro entidades nuevas (ubicaciones de almacén): siembra un
 * almacén vía API porque `seed_empresa_inicial` no lo crea, luego crea la
 * ubicación 100 % vía UI desde /inventario/ubicaciones y la verifica en la lista.
 * El backend de almacenes ya está operativo (prefijo /api/almacenes/); la sesión
 * y la empresa primaria las resuelve `iniciarSesion`.
 */
async function crearAlmacen(api: ApiE2E, empresaId: string, suf: string): Promise<string> {
  const nombre = `Almacén Gaps ${suf}`;
  await api.post<{ id_almacen: string }>('/almacenes/almacenes/', {
    id_empresa: empresaId,
    nombre_almacen: nombre,
    codigo_almacen: `AG${suf}`.slice(0, 20),
  });
  return nombre;
}

test.describe('Gaps menores: ubicaciones de almacén', () => {
  test('crea una ubicación desde la UI y la ve en la lista', async ({ page }) => {
    const { api, empresaId } = await iniciarSesion(page);
    const suf = sufijoUnico();
    const almacenNombre = await crearAlmacen(api, empresaId, suf);
    const codigo = `UB-${suf}`.slice(0, 20);
    const nombre = `Ubicación Gaps ${suf}`;

    await test.step('navegar a la página de Ubicaciones', async () => {
      await page.goto('/inventario/ubicaciones');
      await expect(
        page.getByRole('heading', { name: 'Ubicaciones de Almacén' }),
      ).toBeVisible();
    });

    await test.step('crear una ubicación nueva', async () => {
      await page.getByRole('button', { name: 'Nueva ubicación' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva ubicación' })).toBeVisible();

      await page.getByLabel(/Almacén/).click();
      await page.getByRole('option', { name: almacenNombre }).click();
      await page.getByLabel(/Código/).fill(codigo);
      await page.getByLabel(/Nombre/).fill(nombre);
      await page.getByRole('button', { name: 'Guardar' }).click();

      await expect(page.getByRole('heading', { name: 'Nueva ubicación' })).toBeHidden();
    });

    await test.step('la ubicación aparece en la lista', async () => {
      await expect(page.getByRole('row').filter({ hasText: nombre })).toBeVisible();
      await expect(page.getByRole('row').filter({ hasText: codigo })).toBeVisible();
    });
  });
});
