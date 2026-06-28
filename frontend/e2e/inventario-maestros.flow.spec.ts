import { test, expect } from '@playwright/test';
import { iniciarSesion, type ApiE2E } from './helpers/sesion';
import { sufijoUnico, monedaUsd } from './helpers/datos';

/**
 * Flujo Inventario — Datos Maestros (frontend e2e).
 *
 * Crea una Variante de Producto 100 % vía UI desde la página de Datos Maestros
 * de Inventario, y verifica que la página navega entre sus pestañas (Conversiones
 * UM, Consignación Cliente/Proveedor). El backend de inventario ya está operativo
 * (prefijo /api/inventario/); la sesión y la empresa primaria las resuelve
 * `iniciarSesion`. El producto base y su catálogo (unidad/categoría) se siembran
 * vía API porque `seed_empresa_inicial` no los crea.
 */
async function crearProducto(api: ApiE2E, empresaId: string, suf: string): Promise<string> {
  const usdId = await monedaUsd(api);
  const unidad = await api.post<{ id_unidad_medida: string }>('/inventario/unidades-medida/', {
    id_empresa: empresaId,
    nombre: `Unidad Inv Maestros ${suf}`,
    abreviatura: `UM${suf}`.slice(0, 10),
    tipo: 'CANTIDAD',
  });
  const categoria = await api.post<{ id_categoria_producto: string }>(
    '/inventario/categorias-producto/',
    { id_empresa: empresaId, nombre_categoria: `Categoría Inv Maestros ${suf}` },
  );
  const nombre = `Producto Inv Maestros ${suf}`;
  await api.post<{ id_producto: string }>('/inventario/productos/', {
    id_empresa: empresaId,
    nombre_producto: nombre,
    id_unidad_medida_base: unidad.id_unidad_medida,
    id_categoria: categoria.id_categoria_producto,
    id_moneda_precio: usdId,
    precio_venta_sugerido: '100.00',
    costo_promedio: '50.00',
  });
  return nombre;
}

test.describe('Inventario: datos maestros', () => {
  test('crea una variante desde la UI y navega entre pestañas', async ({ page }) => {
    const { api, empresaId } = await iniciarSesion(page);
    const suf = sufijoUnico();
    const productoNombre = await crearProducto(api, empresaId, suf);
    const codigoVariante = `VAR-${suf}`.slice(0, 20);

    await test.step('crear una variante de producto', async () => {
      await page.goto('/inventario/variantes');
      await expect(
        page.getByRole('heading', { name: 'Datos Maestros de Inventario' }),
      ).toBeVisible();

      await page.getByRole('button', { name: 'Nueva variante' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva variante' })).toBeVisible();

      await page.getByLabel('Producto base').click();
      await page.getByRole('option', { name: productoNombre }).click();
      await page.getByLabel(/Código variante/).fill(codigoVariante);
      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva variante' })).toBeHidden();

      await expect(page.getByRole('row').filter({ hasText: codigoVariante })).toBeVisible();
    });

    await test.step('navegar a Conversiones UM', async () => {
      await page.getByRole('tab', { name: 'Conversiones UM' }).click();
      await expect(page.getByRole('button', { name: 'Nueva conversión' })).toBeVisible();
    });

    await test.step('navegar a Consignación Cliente', async () => {
      await page.getByRole('tab', { name: 'Consignación Cliente' }).click();
      await expect(page.getByRole('button', { name: 'Nueva consignación' })).toBeVisible();
    });

    await test.step('navegar a Consignación Proveedor', async () => {
      await page.getByRole('tab', { name: 'Consignación Proveedor' }).click();
      await expect(page.getByRole('button', { name: 'Nueva consignación' })).toBeVisible();
    });
  });
});
