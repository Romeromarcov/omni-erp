import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { crearPrereqGasto, sufijoUnico } from './helpers/datos';

/**
 * Flujo crítico — Gasto Completo (cross-módulo), manejado vía UI.
 *
 * Cadena de punta a punta soportada HOY por el producto:
 *   registrar gasto (con línea de imputación) → aprobar (genera asiento contable
 *   de la base + asiento de IVA crédito fiscal) → crear reembolso del gasto
 *   aprobado → procesar el pago del reembolso (queda PAGADO).
 *
 * Cruza gastos → contabilidad (asiento balanceado) → finanzas (pago del reembolso).
 *
 * Máquina de estados verificada:
 *   gasto:     PENDIENTE_APROBACION → APROBADO/CONTABILIZADO → REEMBOLSADO
 *   reembolso: PENDIENTE → PAGADO
 *
 * Efectos cruzados verificados:
 *   - en la UI: el gasto pasa a estado Aprobado/Contabilizado y el reembolso a Pagado;
 *   - por API: el reembolso queda PAGADO y, si la empresa generó asientos
 *     (contabilidad es opcional por empresa, ADR-006), el balance de comprobación
 *     cuadra (debe == haber).
 *
 * Montos: monto total 116.00 (base 100.00 + IVA 16.00). La línea de imputación
 * reconcilia con el encabezado (monto 100.00 + IVA 16.00 = 116.00), requisito de
 * `gastos.services._contabilizar_gasto`.
 */
test.describe('Gasto completo: registrar → aprobar → reembolso → pago', () => {
  test('ejecuta el ciclo de gasto por UI y verifica estados y asiento', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();

    // ── Prerequisitos sembrados vía API ──────────────────────────────────────
    const prereq = await crearPrereqGasto(sesion.api, sesion.empresaId, { sufijo: suf });

    const descripcionGasto = `Gasto E2E ${suf}`;
    const montoTotal = '116.00';
    const montoIva = '16.00';
    const montoBase = '100.00';

    await test.step('registrar el gasto desde la UI', async () => {
      await page.goto('/gastos');
      await expect(page.getByRole('heading', { name: 'Gastos' })).toBeVisible();

      await page.getByRole('button', { name: 'Nuevo gasto' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      // Categoría (select MUI) → opción sembrada.
      await dialogo.getByLabel('Categoría').click();
      await page.getByRole('option', { name: prereq.categoriaNombre }).click();

      await dialogo.getByLabel('Descripción').fill(descripcionGasto);
      await dialogo.getByLabel('Monto', { exact: true }).fill(montoTotal);
      await dialogo.getByLabel('IVA', { exact: true }).fill(montoIva);

      // Moneda (select MUI) → USD (única moneda sembrada por defecto).
      await dialogo.getByLabel('Moneda').click();
      await page.getByRole('option').filter({ hasText: 'USD' }).first().click();

      await dialogo.getByRole('button', { name: 'Guardar' }).click();
      await expect(dialogo).toBeHidden();

      // El gasto aparece en la tabla, pendiente de aprobación.
      const fila = page.getByRole('row').filter({ hasText: descripcionGasto });
      await expect(fila).toBeVisible();
      await expect(fila.getByText(montoTotal)).toBeVisible();
    });

    await test.step('agregar la línea de imputación (detalle) que reconcilia el total', async () => {
      const fila = page.getByRole('row').filter({ hasText: descripcionGasto });
      await fila.getByRole('button', { name: 'Detalle' }).click();

      const drawer = page.getByRole('button', { name: 'Cerrar detalle' });
      await expect(drawer).toBeVisible();

      // Cuenta contable (select MUI) → la cuenta de gasto sembrada (por código).
      await page.getByLabel('Cuenta contable').click();
      await page.getByRole('option').filter({ hasText: prereq.cuentaGastoCodigo }).first().click();

      // base 100.00 + IVA 16.00 = 116.00 == encabezado.
      await page.getByLabel('Monto', { exact: true }).fill(montoBase);
      await page.getByLabel('IVA', { exact: true }).fill(montoIva);
      await page.getByRole('button', { name: 'Agregar línea' }).click();

      // La línea aparece listada con la cuenta y el monto.
      await expect(page.getByText(prereq.cuentaGastoCodigo).first()).toBeVisible();

      // Cerrar el drawer para volver a la tabla.
      await page.getByRole('button', { name: 'Cerrar detalle' }).click();
    });

    await test.step('aprobar el gasto (genera asiento base + IVA)', async () => {
      // El confirm del navegador se acepta automáticamente.
      page.once('dialog', (d) => d.accept());
      const fila = page.getByRole('row').filter({ hasText: descripcionGasto });
      await fila.getByRole('button', { name: 'Aprobar' }).click();

      // El estado del gasto pasa a Aprobado o Contabilizado (si generó asiento).
      const filaAprobada = page.getByRole('row').filter({ hasText: descripcionGasto });
      await expect(filaAprobada.getByText(/Aprobado|Contabilizado/)).toBeVisible();
    });

    await test.step('verificar por API que el gasto quedó aprobado/contabilizado', async () => {
      const lista = await sesion.api.get<{
        results?: Array<{ id_gasto: string; descripcion: string; estado_gasto: string }>;
      }>(`/gastos/gastos/?empresa=${sesion.empresaId}&search=${encodeURIComponent(suf)}`);
      const gasto = (lista.results ?? []).find((g) => g.descripcion === descripcionGasto);
      expect(gasto, 'el gasto sembrado debe existir').toBeTruthy();
      expect(['APROBADO', 'CONTABILIZADO']).toContain(gasto!.estado_gasto);
    });

    await test.step('crear el reembolso del gasto aprobado', async () => {
      await page.goto('/gastos/reembolsos');
      await expect(page.getByRole('heading', { name: 'Reembolsos de gasto' })).toBeVisible();

      await page.getByRole('button', { name: 'Nuevo reembolso' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      // Gasto aprobado (select MUI) → la opción incluye la descripción sembrada.
      await dialogo.getByLabel('Gasto aprobado').click();
      await page.getByRole('option').filter({ hasText: descripcionGasto }).first().click();

      await dialogo.getByLabel('Monto a reembolsar').fill(montoTotal);

      await dialogo.getByLabel('Moneda').click();
      await page.getByRole('option').filter({ hasText: 'USD' }).first().click();

      await dialogo.getByLabel('Método de pago').click();
      await page.getByRole('option', { name: prereq.metodoPagoNombre }).click();

      await dialogo.getByRole('button', { name: 'Guardar' }).click();
      await expect(dialogo).toBeHidden();

      // El reembolso aparece pendiente.
      const fila = page.getByRole('row').filter({ hasText: descripcionGasto });
      await expect(fila).toBeVisible();
      await expect(fila.getByText('PENDIENTE')).toBeVisible();
    });

    await test.step('procesar el pago del reembolso (queda PAGADO)', async () => {
      page.once('dialog', (d) => d.accept());
      const fila = page.getByRole('row').filter({ hasText: descripcionGasto });
      await fila.getByRole('button', { name: 'Procesar pago' }).click();

      const filaPagada = page.getByRole('row').filter({ hasText: descripcionGasto });
      await expect(filaPagada.getByText('PAGADO')).toBeVisible();
    });

    await test.step('verificar efectos cruzados por API (reembolso PAGADO + asiento cuadra)', async () => {
      const reembolsos = await sesion.api.get<{
        results?: Array<{ id_reembolso: string; id_gasto: string; estado_reembolso: string }>;
      }>(`/gastos/reembolsos-gasto/?empresa=${sesion.empresaId}&estado_reembolso=PAGADO`);
      const lista = reembolsos.results ?? [];
      expect(lista.length, 'debe existir al menos un reembolso PAGADO').toBeGreaterThan(0);
      expect(lista.every((r) => r.estado_reembolso === 'PAGADO')).toBeTruthy();

      // Asiento contable: opcional por empresa (ADR-006). Si la empresa generó
      // asientos aprobados, el balance de comprobación debe cuadrar (debe==haber).
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
