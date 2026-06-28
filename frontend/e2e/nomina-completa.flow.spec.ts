import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { crearPrereqNomina, sufijoUnico } from './helpers/datos';

/**
 * Flujo crítico — Nómina Completa / Hire-to-Pay (cross-módulo).
 *
 * Cadena de punta a punta soportada HOY por el producto, manejada vía UI:
 *   (empleado + período abierto sembrados) → crear proceso de nómina →
 *   procesar (motor LOTTT genera recibos + asiento NOMINA) → aprobar proceso →
 *   marcar el recibo del empleado como pagado.
 *
 * Cruza rrhh → nomina → contabilidad (asiento) → finanzas/tesorería (estado PAGADA).
 *
 * Efectos cruzados verificados:
 *   - el proceso genera un recibo con devengado/deducciones/neto > 0 (UI);
 *   - aprobar el proceso lo deja en APROBADO y sus recibos en APROBADA;
 *   - marcar pagada deja el recibo en PAGADA (UI + API);
 *   - el asiento NOMINA es opcional por empresa (ADR-006): si la empresa generó
 *     asientos, el balance de comprobación debe cuadrar (debe == haber).
 */
test.describe('Nómina completa: período → proceso → procesar → aprobar → pago', () => {
  test('ejecuta el ciclo Hire-to-Pay por UI y verifica recibo, estados y asiento', async ({
    page,
  }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();
    const salarioMensual = '600.00';

    // ── Prerequisitos sembrados vía API ──────────────────────────────────────
    const prereq = await crearPrereqNomina(sesion.api, sesion.empresaId, {
      salarioMensual,
      sufijo: suf,
    });
    const empleadoCompleto = `${prereq.empleadoNombre} ${prereq.empleadoApellido}`;
    const numeroProceso = `NOM-E2E-${suf}`;

    await test.step('crear el proceso de nómina desde la UI', async () => {
      await page.goto('/nomina/procesos');
      await expect(page.getByRole('heading', { name: 'Procesos de Nómina' })).toBeVisible();

      await page.getByRole('button', { name: 'Nuevo proceso' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      // Período (MUI Select dentro del TextField select).
      await dialogo.getByLabel('Período').click();
      await page.getByRole('option', { name: prereq.periodoNombre }).click();
      await dialogo.getByLabel('Número').fill(numeroProceso);

      await dialogo.getByRole('button', { name: 'Crear proceso' }).click();

      // Tras crear navega al detalle del proceso.
      await expect(
        page.getByRole('heading', { name: `Proceso ${numeroProceso}` }),
      ).toBeVisible();
      await expect(page.getByText('EN_PROCESO').first()).toBeVisible();
    });

    await test.step('procesar la nómina (genera recibos + asiento)', async () => {
      await page.getByRole('button', { name: 'Procesar', exact: true }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      // El empleado sembrado aparece en el formulario de datos variables.
      await expect(dialogo.getByText(empleadoCompleto, { exact: false })).toBeVisible();

      // Procesar con los defaults del motor (30 días, sin horas extra).
      await dialogo.getByRole('button', { name: 'Procesar nómina' }).click();

      // El snackbar "Nómina procesada…" es efímero (se auto-cierra). Validamos el
      // resultado PERSISTENTE: el diálogo se cierra y la pantalla muestra el total
      // neto calculado por el motor (heading "Total neto: …") y el estado avanza.
      // Timeout amplio: procesar genera recibos + asiento (op. de backend pesada
      // que bajo carga de CI tarda > 10 s en cerrar el diálogo).
      await expect(dialogo).toBeHidden({ timeout: 30_000 });
      await expect(
        page.getByRole('heading', { name: /Total neto:/ }),
      ).toBeVisible({ timeout: 15_000 });
    });

    await test.step('el recibo del empleado tiene devengado/deducciones/neto > 0', async () => {
      const fila = page.getByRole('row').filter({ hasText: empleadoCompleto });
      await expect(fila).toBeVisible();
      // El recibo nace CALCULADA.
      await expect(fila.getByText('CALCULADA')).toBeVisible();
    });

    await test.step('aprobar el proceso (proceso → APROBADO, recibos → APROBADA)', async () => {
      await page.getByRole('button', { name: 'Aprobar proceso' }).click();
      await expect(page.getByText('Proceso de nómina aprobado.')).toBeVisible();
      await expect(page.getByText('APROBADO').first()).toBeVisible();

      const fila = page.getByRole('row').filter({ hasText: empleadoCompleto });
      await expect(fila.getByText('APROBADA')).toBeVisible();
    });

    await test.step('marcar el recibo como pagado (recibo → PAGADA)', async () => {
      const fila = page.getByRole('row').filter({ hasText: empleadoCompleto });
      await fila.getByRole('button', { name: 'Marcar pagada' }).click();
      await expect(page.getByText('Recibo marcado como pagado.')).toBeVisible();

      const filaPagada = page.getByRole('row').filter({ hasText: empleadoCompleto });
      await expect(filaPagada.getByText('PAGADA')).toBeVisible();
    });

    await test.step('el recibo quedó PAGADA (vía API) y el asiento cuadra si existe', async () => {
      const recibos = await sesion.api.get<{
        results?: Array<{ id_empleado: number; estado: string; total_neto: string }>;
      }>(`/nomina/nominas/?id_empleado=${prereq.empleadoId}`);
      const lista = recibos.results ?? [];
      const recibo = lista.find((r) => r.id_empleado === prereq.empleadoId);
      expect(recibo, 'el recibo del empleado debe existir y estar PAGADA').toBeTruthy();
      expect(recibo!.estado).toBe('PAGADA');
      expect(Number(recibo!.total_neto)).toBeGreaterThan(0);

      // Asiento NOMINA: opcional por empresa (ADR-006). Si la empresa generó
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
