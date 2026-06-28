import { test, expect } from '@playwright/test';
import { iniciarSesion, type ApiE2E } from './helpers/sesion';
import { sufijoUnico, monedaUsd } from './helpers/datos';

/**
 * Flujo Manufactura — Datos Maestros (frontend e2e).
 *
 * Crea un Centro de Trabajo y una Lista de Materiales (BOM) con un componente,
 * 100 % vía UI desde la página de Datos Maestros. El backend de manufactura ya
 * está operativo (prefijo /api/manufactura/); la sesión y la empresa primaria
 * las resuelve `iniciarSesion`. Los productos y la unidad de medida (catálogo de
 * inventario que no siembra `seed_empresa_inicial`) se crean vía API.
 */

/** Siembra una unidad de medida + un producto terminado + un componente. */
async function crearProductosBom(
  api: ApiE2E,
  empresaId: string,
  suf: string,
): Promise<{ unidadAbrev: string; productoFinal: string; componente: string }> {
  const usdId = await monedaUsd(api);
  const unidadAbrev = `UM${suf}`.slice(0, 10);
  const unidad = await api.post<{ id_unidad_medida: string }>('/inventario/unidades-medida/', {
    id_empresa: empresaId,
    nombre: `Unidad Maestros ${suf}`,
    abreviatura: unidadAbrev,
    tipo: 'CANTIDAD',
  });
  const categoria = await api.post<{ id_categoria_producto: string }>(
    '/inventario/categorias-producto/',
    { id_empresa: empresaId, nombre_categoria: `Categoría Maestros ${suf}` },
  );
  const crearProd = async (nombre: string): Promise<string> => {
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
  };
  const productoFinal = await crearProd(`Mueble Maestros ${suf}`);
  const componente = await crearProd(`Tabla Maestros ${suf}`);
  return { unidadAbrev, productoFinal, componente };
}

test.describe('Manufactura: datos maestros', () => {
  test('crea un centro de trabajo y una BOM con un componente desde la UI', async ({ page }) => {
    const { api, empresaId } = await iniciarSesion(page);
    const suf = sufijoUnico();
    const { unidadAbrev, productoFinal, componente } = await crearProductosBom(api, empresaId, suf);

    const codigoCentro = `CT${suf}`.slice(0, 20);
    const nombreCentro = `Centro Maestros ${suf}`;
    const nombreBom = `BOM Maestros ${suf}`;

    await test.step('crear un centro de trabajo', async () => {
      await page.goto('/manufactura/centros-trabajo');
      await expect(page.getByRole('heading', { name: 'Datos Maestros de Manufactura' })).toBeVisible();
      await page.getByRole('tab', { name: 'Centros de Trabajo' }).click();

      await page.getByRole('button', { name: 'Nuevo centro de trabajo' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo centro de trabajo' })).toBeVisible();
      await page.getByLabel(/Código/).fill(codigoCentro);
      await page.getByLabel(/Nombre/).fill(nombreCentro);
      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo centro de trabajo' })).toBeHidden();

      await expect(page.getByRole('row').filter({ hasText: nombreCentro })).toBeVisible();
    });

    await test.step('crear una BOM con un componente', async () => {
      await page.goto('/manufactura/listas-materiales');
      await page.getByRole('tab', { name: 'Listas de Materiales' }).click();

      await page.getByRole('button', { name: 'Nueva lista de materiales' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva lista de materiales' })).toBeVisible();
      await page.getByLabel(/Nombre/).fill(nombreBom);
      await page.getByLabel(/Producto a fabricar/).click();
      await page.getByRole('option', { name: productoFinal }).click();
      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva lista de materiales' })).toBeHidden();

      const fila = page.getByRole('row').filter({ hasText: nombreBom });
      await expect(fila).toBeVisible();

      await fila.getByRole('button', { name: 'Componentes' }).click();
      await expect(page.getByText('Componentes del BOM')).toBeVisible();

      await page.getByRole('combobox', { name: 'Componente', exact: true }).click();
      await page.getByRole('option', { name: componente }).click();
      await page.getByLabel('Cantidad requerida').fill('3');
      await page.getByLabel(/Unidad/).click();
      await page.getByRole('option', { name: unidadAbrev, exact: false }).click();
      await page.getByRole('button', { name: 'Agregar componente' }).click();

      // El componente aparece en la lista del drawer.
      await expect(page.getByText(componente, { exact: false })).toBeVisible();
    });
  });
});
