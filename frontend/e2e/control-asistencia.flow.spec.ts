import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Control de Asistencia — horario → asignación → marcaje (frontend e2e).
 *
 * Siembra un empleado vía API (prefijo /api/rrhh/), luego opera 100 % desde la
 * UI de Control de Asistencia: crea un horario de trabajo, lo asigna al empleado
 * y registra un marcaje de entrada. Verifica que cada paso aparece en su tabla.
 *
 * La sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Control de Asistencia: horario → asignación → marcaje', () => {
  test('crea horario, lo asigna a un empleado y marca asistencia', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const { api, empresaId } = sesion;

    const suf = sufijoUnico();
    const horarioNombre = `Horario E2E ${suf}`;
    const nombreEmpleado = `Asist${suf}`.slice(0, 20);
    const apellidoEmpleado = `Test${suf}`.slice(0, 20);
    const nombreCompleto = `${nombreEmpleado} ${apellidoEmpleado}`;

    await test.step('sembrar empleado vía API', async () => {
      await api.post('/rrhh/empleados/', {
        empresa: empresaId,
        nombre: nombreEmpleado,
        apellido: apellidoEmpleado,
        cedula: `V-${String(Date.now()).slice(-8)}`,
        fecha_ingreso: new Date().toISOString().slice(0, 10),
        activo: true,
      });
    });

    await test.step('navegar a Control de Asistencia', async () => {
      await page.goto('/control-asistencia');
      await expect(
        page.getByRole('heading', { name: 'Control de Asistencia' }),
      ).toBeVisible();
    });

    await test.step('crear un horario de trabajo', async () => {
      await page.getByRole('button', { name: 'Nuevo horario' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo horario' })).toBeVisible();
      await page.getByLabel(/Nombre del horario/).fill(horarioNombre);
      await page.getByLabel(/Total de horas semanales/).fill('40.00');
      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo horario' })).toBeHidden();
      await expect(page.getByRole('row').filter({ hasText: horarioNombre })).toBeVisible();
    });

    await test.step('asignar el horario al empleado', async () => {
      await page.getByRole('tab', { name: 'Asignaciones' }).click();
      await page.getByRole('button', { name: 'Nueva asignación' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva asignación' })).toBeVisible();

      const dialogo = page.getByRole('dialog');
      await dialogo.getByLabel(/Empleado/).click();
      await page.getByRole('option', { name: nombreCompleto }).click();
      await dialogo.getByLabel(/Horario/).click();
      await page.getByRole('option', { name: horarioNombre }).click();

      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nueva asignación' })).toBeHidden();
      await expect(page.getByRole('row').filter({ hasText: nombreCompleto })).toBeVisible();
    });

    await test.step('marcar asistencia del empleado', async () => {
      await page.getByRole('tab', { name: 'Registros' }).click();
      await page.getByLabel('Empleado').click();
      await page.getByRole('option', { name: nombreCompleto }).click();

      await page.getByRole('button', { name: 'Marcar asistencia' }).click();
      await expect(page.getByRole('heading', { name: 'Marcar asistencia' })).toBeVisible();
      await page.getByRole('button', { name: 'Registrar marcaje' }).click();
      await expect(page.getByRole('heading', { name: 'Marcar asistencia' })).toBeHidden();

      await expect(page.getByRole('row').filter({ hasText: 'Entrada' })).toBeVisible();
    });
  });
});
