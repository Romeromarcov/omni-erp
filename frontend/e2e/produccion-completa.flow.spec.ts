import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { crearPrereqProduccion, sufijoUnico } from './helpers/datos';

/**
 * Flujo crítico — Producción Completa / Produce-to-Cost (cross-módulo).
 *
 * Cadena de punta a punta soportada por el producto, manejada vía UI:
 *   crear OF → consumir materiales (descuenta inventario) → avanzar etapas →
 *   completar OF (entrada de PT al costo real + costo de producción persistido).
 *
 * Cruza manufactura → inventario → costos → contabilidad.
 *
 * Efectos cruzados verificados:
 *   - el stock de la materia prima BAJA tras el consumo (pantalla Stock Actual);
 *   - el producto terminado entra al inventario al cerrar la OF (Stock Actual SUBE);
 *   - el costo de producción queda persistido (CostoProduccion vía API);
 *   - el asiento contable, si la empresa lo genera (ADR-006), cuadra (debe==haber).
 */
test.describe.serial('Producción completa: OF → consumo → etapas → cierre', () => {
  test('ejecuta el ciclo Produce-to-Cost por UI y verifica stock, costo y asiento', async ({
    page,
  }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();

    // ── Prerequisitos sembrados vía API ──────────────────────────────────────
    // Materia prima: 100 en stock; BOM consume 5 por unidad de producto terminado.
    const prereq = await crearPrereqProduccion(sesion.api, sesion.empresaId, {
      stockMateriaPrima: '100',
      cantidadPorUnidad: '5',
      sufijo: suf,
    });

    // Catálogo de etapas estándar de la empresa (corte → … → control final): la
    // OF las materializa al crearse y deben completarse antes del cierre.
    await sesion.api.post('/manufactura/etapas-produccion/crear-estandar/', {});

    const cantidadOF = '4'; // 4 unidades → consumo de materia prima = 4 * 5 = 20.
    const referencia = `OF-E2E-${suf}`;
    // Materia prima: 100 inicial − 20 consumidas = 80 disponibles.
    const stockMpFinal = '80';

    let ordenId = '';

    await test.step('crear la orden de producción desde la UI', async () => {
      await page.goto('/manufactura/ordenes');
      await page.getByRole('button', { name: 'Nueva orden' }).click();
      await expect(
        page.getByRole('heading', { name: 'Nueva Orden de Producción' }),
      ).toBeVisible();

      await page.getByLabel('Producto terminado').click();
      await page.getByRole('option', { name: prereq.productoTerminadoNombre }).click();
      await page.getByLabel('Cantidad a producir').fill(cantidadOF);

      await page.getByLabel('Lista de materiales (BOM)').click();
      await page.getByRole('option', { name: `BOM ${prereq.productoTerminadoNombre}` }).click();

      await page.getByLabel('Referencia', { exact: true }).fill(referencia);

      await page.getByRole('button', { name: 'Crear orden' }).click();

      // Tras crear navega al detalle de la OF.
      await expect(
        page.getByRole('heading', { name: `Orden de Producción ${referencia}` }),
      ).toBeVisible();
      ordenId = page.url().split('/manufactura/ordenes/')[1];
      expect(ordenId, 'la OF creada debe tener id en la URL').toBeTruthy();
    });

    await test.step('consumir materiales (descuenta el inventario de la materia prima)', async () => {
      await page.getByRole('button', { name: 'Consumir materiales' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      await dialogo.getByLabel('Almacén').click();
      await page.getByRole('option', { name: prereq.almacenNombre }).click();

      await dialogo.getByRole('button', { name: 'Consumir materiales' }).click();
      await expect(page.getByText(/Materiales consumidos por/)).toBeVisible();
    });

    await test.step('el stock de la materia prima bajó a 80 en Stock Actual', async () => {
      await page.goto('/inventario/stock');
      await page.getByPlaceholder('Buscar producto…').fill(prereq.materiaPrimaNombre);
      const fila = page.getByRole('row').filter({ hasText: prereq.materiaPrimaNombre });
      await expect(fila).toBeVisible();
      await expect(fila.getByRole('cell', { name: stockMpFinal, exact: true })).toBeVisible();
    });

    await test.step('avanzar todas las etapas de fabricación', async () => {
      await page.goto(`/manufactura/ordenes/${ordenId}`);
      await expect(page.getByRole('heading', { name: 'Etapas de fabricación' })).toBeVisible();

      // Completa cada etapa pendiente con horas × tarifa (mano de obra real).
      // El botón "Avanzar etapa" se deshabilita cuando ya no quedan pendientes.
      const botonAvanzar = page.getByRole('button', { name: 'Avanzar etapa' });
      for (let i = 0; i < 6; i += 1) {
        if (await botonAvanzar.isDisabled()) break;
        await botonAvanzar.click();
        const dialogo = page.getByRole('dialog');
        await expect(dialogo).toBeVisible();
        await dialogo.getByLabel('Horas trabajadas').fill('1');
        await dialogo.getByLabel('Tarifa por hora').fill('10');
        await dialogo.getByRole('button', { name: 'Confirmar' }).click();
        await expect(page.getByText('Etapa completada correctamente.')).toBeVisible();
        // Espera a que el diálogo se cierre antes de la siguiente iteración.
        await expect(dialogo).toBeHidden();
      }
      // Ya no quedan etapas pendientes: el botón queda deshabilitado.
      await expect(botonAvanzar).toBeDisabled();
    });

    await test.step('completar la OF (entrada de PT al costo real)', async () => {
      await page.getByRole('button', { name: 'Completar OF' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      await dialogo.getByLabel('Almacén').click();
      await page.getByRole('option', { name: prereq.almacenNombre }).click();

      await dialogo.getByRole('button', { name: 'Confirmar' }).click();
      await expect(
        page.getByText('Orden completada: producción terminada registrada.'),
      ).toBeVisible();
    });

    await test.step('el producto terminado entró al inventario (Stock Actual = 4)', async () => {
      await page.goto('/inventario/stock');
      await page.getByPlaceholder('Buscar producto…').fill(prereq.productoTerminadoNombre);
      const fila = page.getByRole('row').filter({ hasText: prereq.productoTerminadoNombre });
      await expect(fila).toBeVisible();
      await expect(fila.getByRole('cell', { name: cantidadOF, exact: true })).toBeVisible();
    });

    await test.step('el costo de producción quedó persistido y el asiento cuadra si existe', async () => {
      // CostoProduccion materializado al cerrar la OF (materiales + MO + overhead).
      const costos = await sesion.api.get<{
        results?: Array<{ id_orden_produccion: string; tipo_costo: string; costo_total: string }>;
      }>(`/costos/costos-produccion/?id_orden_produccion=${ordenId}`);
      const lista = (costos.results ?? []).filter((c) => c.id_orden_produccion === ordenId);
      expect(lista.length, 'la OF cerrada debe persistir costos de producción').toBeGreaterThan(0);

      // El material directo costeado debe ser > 0 (20 unidades de MP @ 7.00 = 140).
      const material = lista.find((c) => c.tipo_costo === 'MATERIAL_DIRECTO');
      expect(material, 'debe existir el costo de material directo').toBeTruthy();
      expect(Number(material!.costo_total)).toBeGreaterThan(0);

      // Asiento contable: opcional por empresa (ADR-006). Si la empresa generó
      // asientos, el balance de comprobación debe cuadrar (debe == haber).
      const balance = await sesion.api.get<{
        total_debe?: string;
        total_haber?: string;
      }>(`/contabilidad/asientos-contables/balance_comprobacion/?empresa_id=${sesion.empresaId}`);
      if (balance.total_debe !== undefined && balance.total_haber !== undefined) {
        expect(Number(balance.total_debe)).toBeCloseTo(Number(balance.total_haber), 2);
      }
    });
  });
});
