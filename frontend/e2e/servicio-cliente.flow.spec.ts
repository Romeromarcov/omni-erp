import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { sufijoUnico } from './helpers/datos';

/**
 * Flujo Servicio al Cliente — mesa de ayuda (frontend e2e).
 *
 * Siembra una categoría de ticket vía API (prefijo /api/servicio-cliente/),
 * registra un ticket 100 % desde la UI de la página de Tickets, abre su detalle,
 * agrega un comentario y cambia su estado a "En progreso", verificando que el
 * chip de estado se actualiza.
 *
 * La sesión y la empresa primaria las resuelve `iniciarSesion`.
 */
test.describe('Servicio al Cliente: ticket, comentario y cambio de estado', () => {
  test('crea un ticket, agrega un comentario y cambia su estado', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const { api, empresaId } = sesion;

    const suf = sufijoUnico();
    const numero = `T-E2E-${suf}`;
    const asunto = `Ticket E2E ${suf}`;
    const categoriaNombre = `Categoría Ticket E2E ${suf}`;

    await test.step('sembrar categoría de ticket', async () => {
      await api.post('/servicio-cliente/categorias-ticket/', {
        id_empresa: empresaId,
        nombre_categoria: categoriaNombre,
        activo: true,
      });
    });

    await test.step('navegar a la página de Tickets', async () => {
      await page.goto('/servicio-cliente/tickets');
      await expect(page.getByRole('heading', { name: 'Tickets de soporte' })).toBeVisible();
    });

    await test.step('registrar un ticket nuevo', async () => {
      await page.getByRole('button', { name: 'Nuevo ticket' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo ticket' })).toBeVisible();

      await page.getByLabel(/Número de ticket/).fill(numero);

      // Categoría (selector MUI).
      await page.getByLabel(/Categoría/).click();
      await page.getByRole('option', { name: categoriaNombre }).click();

      await page.getByLabel(/Asunto/).fill(asunto);
      await page.getByLabel(/Descripción/).fill('Descripción del problema E2E');

      await page.getByRole('button', { name: 'Guardar' }).click();
      await expect(page.getByRole('heading', { name: 'Nuevo ticket' })).toBeHidden();
    });

    await test.step('el ticket aparece en la lista', async () => {
      const fila = page.getByRole('row').filter({ hasText: numero });
      await expect(fila).toBeVisible();
      await expect(fila.getByText('Abierto')).toBeVisible();
    });

    await test.step('abrir el detalle y agregar un comentario', async () => {
      const fila = page.getByRole('row').filter({ hasText: numero });
      await fila.getByRole('button', { name: 'Detalle' }).click();

      await expect(page.getByRole('heading', { name: `Ticket ${numero}` })).toBeVisible();
      await page.getByLabel(/Agregar comentario/).fill('Comentario desde E2E');
      await page.getByRole('button', { name: 'Agregar comentario' }).click();

      await expect(page.getByText('Comentario desde E2E')).toBeVisible();
    });

    await test.step('cambiar el estado a En progreso', async () => {
      await page.getByLabel(/Nuevo estado/).click();
      await page.getByRole('option', { name: 'En progreso' }).click();
      await page.getByRole('button', { name: 'Cambiar estado' }).click();

      // El estado del ticket se refleja en los chips del detalle.
      await expect(page.getByText('En progreso').first()).toBeVisible();
    });
  });
});
