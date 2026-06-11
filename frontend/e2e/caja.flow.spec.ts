import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import {
  cajaVirtualPrincipal,
  crearCatalogoInventario,
  crearCliente,
  crearPedido,
  registrarPagoEnCaja,
  sufijoUnico,
} from './helpers/datos';

/**
 * Flujo crítico 3 — Caja (TEST-6 / Fase 4).
 *
 * Sustituye al flujo de compras (OC→recepción→factura), que hoy es API-only:
 * el frontend no tiene ninguna ruta de compras (auditoría 2026-06-10).
 *
 * Alcance real soportado hoy: pago en efectivo sobre un pedido → movimiento de
 * caja, verificado en la UI (detalle del pedido y movimientos de la caja).
 * El pago se registra vía API porque el ModalPago de la UI exige tasa BCV del
 * día para habilitar "Confirmar", y la apertura/cierre de sesión de caja está
 * rota en el backend (gaps documentados en el PR):
 *   - el botón "Abrir sesión" llama `POST /finanzas/cajas-fisicas/{id}/abrir-sesion/`,
 *     que NO existe (404);
 *   - `POST /finanzas/sesiones-caja/` revienta con FieldError 500 (`es_fisica`
 *     no es un campo de Caja).
 */
test.describe('Caja: pago de pedido → movimiento de caja', () => {
  test('registra un pago en efectivo y lo ve en el pedido y en la caja', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();
    // Monto con céntimos pseudo-únicos para localizarlo sin ambigüedad en la UI.
    const monto = (50 + Math.floor(Math.random() * 4000) / 100).toFixed(2);

    const catalogo = await crearCatalogoInventario(sesion.api, sesion.empresaId, {
      stockInicial: '20',
      sufijo: suf,
    });
    const cliente = await crearCliente(sesion.api, sesion.empresaId, suf);
    const pedido = await crearPedido(sesion.api, {
      clienteId: cliente.clienteId,
      productoId: catalogo.productoId,
      cantidad: '1',
      precioUnitario: monto,
    });
    const caja = await cajaVirtualPrincipal(sesion.api, sesion.empresaId);

    await test.step('registrar pago en efectivo contra la caja (API)', async () => {
      const pago = await registrarPagoEnCaja(sesion.api, {
        empresaId: sesion.empresaId,
        pedidoId: pedido.pedidoId,
        cajaVirtualId: caja.id_caja,
        monedaUsdId: catalogo.monedaUsdId,
        monto,
      });
      expect(pago.id_pago).toBeTruthy();
    });

    await test.step('el detalle del pedido lista el pago', async () => {
      await page.goto(`/ventas/pedidos/${pedido.pedidoId}`);
      await expect(
        page.getByRole('heading', { name: `Pedido ${pedido.numeroPedido}` }),
      ).toBeVisible();
      await expect(page.getByText('Pagos')).toBeVisible();
      // El listado muestra "<método> - <moneda> <monto> - Tasa: ...". Gap UI
      // documentado en el PR: hoy renderiza los UUID del método/moneda (el
      // serializer no expone `id_metodo_pago_obj`), así que se localiza el
      // pago por su monto (4 decimales) y tasa.
      const montoEnLista = `${monto}00 - Tasa: 1.0000`;
      await expect(page.getByText(montoEnLista)).toBeVisible();
    });

    await test.step('los movimientos de la caja muestran el ingreso', async () => {
      await page.goto(`/cajas/${caja.id_caja}/movimientos-caja-banco`);
      await expect(page.getByRole('heading', { name: 'Movimientos de Caja' })).toBeVisible();
      await expect(page.getByRole('cell', { name: monto, exact: true }).first()).toBeVisible();
    });
  });
});
