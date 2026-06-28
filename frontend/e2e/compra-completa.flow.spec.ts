import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { crearProducto, crearProveedor, sufijoUnico } from './helpers/datos';

/**
 * Flujo crítico — Compra Completa / Procure-to-Pay (cross-módulo).
 *
 * Cadena de punta a punta soportada HOY por el producto, manejada vía UI:
 *   crear OC → aprobar → recepcionar (entrada de inventario + CxP) →
 *   registrar factura del proveedor → abonar la CxP hasta saldarla.
 *
 * Cruza compras → inventario → cuentas_por_pagar → finanzas → contabilidad.
 *
 * Efectos cruzados verificados en la UI real:
 *   - el stock del producto sube tras la recepción (pantalla Stock Actual);
 *   - la CxP nace de la recepción y aparece en Cuentas por Pagar;
 *   - el abono la deja en saldo 0 / estado PAGADA.
 * El asiento contable (RECEPCION_MERCANCIA) sólo es observable por API; se valida
 * de forma condicional (la contabilidad es opcional por empresa, ADR-006): si la
 * empresa generó asientos, se exige que cuadren (debe == haber).
 */
test.describe('Compra completa: OC → recepción → factura → CxP → pago', () => {
  test('ejecuta el ciclo P2P por UI y verifica stock, CxP y asiento', async ({ page }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();

    // ── Prerequisitos sembrados vía API ──────────────────────────────────────
    const proveedor = await crearProveedor(sesion.api, sesion.empresaId, suf);
    const { productoId, productoNombre } = await crearProducto(sesion.api, sesion.empresaId, suf);
    const almacen = await sesion.api.post<{ id_almacen: string; nombre_almacen: string }>(
      '/almacenes/almacenes/',
      {
        id_empresa: sesion.empresaId,
        nombre_almacen: `Almacén E2E ${suf}`,
        codigo_almacen: `E2E${suf}`.slice(0, 10),
      },
    );
    // Carga inicial de stock para tener una línea base observable en Stock Actual.
    await sesion.api.post('/inventario/movimientos-inventario/', {
      id_empresa: sesion.empresaId,
      id_producto: productoId,
      tipo_movimiento: 'AJUSTE',
      cantidad: '20',
      fecha_hora_movimiento: new Date().toISOString(),
      id_almacen_destino: almacen.id_almacen,
      costo_unitario_movimiento: '25.00',
      observaciones: `Carga inicial P2P E2E ${suf}`,
    });

    const numeroOrden = `OC-E2E-${suf}`;
    // Cantidad a recibir = 10 → stock final esperado = 20 + 10 = 30.
    const cantidad = '10';
    const costoUnitario = '25.00';
    const montoEsperado = '250.00'; // 10 * 25.00

    await test.step('crear la orden de compra desde la UI', async () => {
      await page.goto('/compras/ordenes/nueva');
      await expect(page.getByRole('heading', { name: 'Nueva Orden de Compra' })).toBeVisible();

      // Proveedor (select MUI) y cabecera.
      await page.getByLabel('Proveedor').click();
      await page.getByRole('option', { name: proveedor.razonSocial }).click();
      await page.getByLabel('Número de orden').fill(numeroOrden);

      // Primera (y única) línea: producto + cantidad + precio.
      await page.getByRole('cell').getByLabel('Producto').first().click();
      await page.getByRole('option', { name: productoNombre }).click();
      await page.getByLabel('Cantidad').first().fill(cantidad);
      await page.getByLabel('Precio unitario').first().fill(costoUnitario);

      await page.getByRole('button', { name: 'Crear orden' }).click();

      // Tras crear navega al detalle de la OC.
      await expect(
        page.getByRole('heading', { name: `Orden de Compra ${numeroOrden}` }),
      ).toBeVisible();
      await expect(page.getByText('BORRADOR')).toBeVisible();
    });

    await test.step('aprobar la orden', async () => {
      await page.getByRole('button', { name: 'Aprobar', exact: true }).click();
      await expect(page.getByText('Orden aprobada.')).toBeVisible();
      await expect(page.getByText('APROBADA', { exact: true })).toBeVisible();
    });

    await test.step('recepcionar la mercancía (entrada de inventario + CxP)', async () => {
      await page.getByRole('button', { name: 'Recepcionar mercancía' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();

      await dialogo.getByLabel('Almacén').click();
      await page.getByRole('option', { name: almacen.nombre_almacen }).click();

      // La cantidad y el costo vienen precargados desde la línea de la OC; se
      // reescriben explícitamente para no depender del prefill.
      await dialogo.getByLabel('Cantidad recibida').fill(cantidad);
      await dialogo.getByLabel('Costo unitario').fill(costoUnitario);

      await dialogo.getByRole('button', { name: 'Registrar recepción' }).click();

      await expect(page.getByText(/Recepción registrada por/)).toBeVisible();
      // La recepción aparece en el bloque "Recepciones de mercancía".
      await expect(page.getByText(montoEsperado).first()).toBeVisible();
    });

    await test.step('el stock del producto subió a 30 en Stock Actual', async () => {
      await page.goto('/inventario/stock');
      await page.getByPlaceholder('Buscar producto…').fill(productoNombre);
      const fila = page.getByRole('row').filter({ hasText: productoNombre });
      await expect(fila).toBeVisible();
      // 20 (carga inicial) + 10 (recepción) = 30 disponibles.
      await expect(fila.getByRole('cell', { name: '30', exact: true })).toBeVisible();
    });

    await test.step('registrar la factura del proveedor sobre la recepción', async () => {
      await page.goto(`/compras/ordenes`);
      const fila = page.getByRole('row').filter({ hasText: numeroOrden });
      await expect(fila).toBeVisible();
      await fila.click();
      await expect(
        page.getByRole('heading', { name: `Orden de Compra ${numeroOrden}` }),
      ).toBeVisible({ timeout: 20_000 });

      // El botón "Registrar factura" se habilita cuando la query de recepciones
      // de la OC resuelve con ≥1 recepción. Si la query falla por un hipo
      // transitorio del backend (timeout de conexión a la BD bajo carga, 5xx),
      // React Query cachea el resultado vacío durante `staleTime`; un reload
      // fuerza un refetch limpio. Reintentamos hasta que el botón se habilite.
      const botonFactura = page.getByRole('button', { name: 'Registrar factura' });
      await expect(async () => {
        if (await botonFactura.isDisabled()) {
          await page.reload();
          await expect(
            page.getByRole('heading', { name: `Orden de Compra ${numeroOrden}` }),
          ).toBeVisible();
        }
        await expect(botonFactura).toBeEnabled({ timeout: 5_000 });
      }).toPass({ timeout: 60_000 });

      await botonFactura.click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();
      const numeroFactura = `FAC-${suf}`;
      await dialogo.getByLabel('Número de factura').fill(numeroFactura);
      await dialogo.getByRole('button', { name: 'Registrar factura' }).click();

      await expect(page.getByText(`Factura ${numeroFactura} registrada.`)).toBeVisible({
        timeout: 20_000,
      });
    });

    await test.step('la CxP generada aparece y se salda con un abono', async () => {
      // La CxP nacida en la recepción lleva en observaciones "Recepción OC {numero}".
      await page.goto('/compras/cuentas-por-pagar');
      await expect(page.getByRole('heading', { name: 'Cuentas por Pagar' })).toBeVisible();

      const referencia = `Recepción OC ${numeroOrden}`;
      const fila = page.getByRole('row').filter({ hasText: referencia });
      // La CxP nace de la recepción de forma asíncrona; bajo carga de CI tarda.
      await expect(fila).toBeVisible({ timeout: 20_000 });
      // Saldo pendiente = monto total = 250.00 antes del abono.
      await expect(fila.getByText(montoEsperado).first()).toBeVisible();

      await fila.getByRole('button', { name: 'Abonar' }).click();
      const dialogo = page.getByRole('dialog');
      await expect(dialogo).toBeVisible();
      await dialogo.getByLabel('Monto').fill(montoEsperado);
      await dialogo.getByRole('button', { name: 'Registrar abono' }).click();

      await expect(page.getByText('Abono registrado correctamente.')).toBeVisible({
        timeout: 20_000,
      });

      // Tras saldarla queda en estado PAGADA y sin acción de abono disponible.
      await page.getByText('Filtrar por estado').click();
      await page.getByRole('option', { name: 'PAGADA' }).click();
      const filaPagada = page.getByRole('row').filter({ hasText: referencia });
      await expect(filaPagada).toBeVisible();
      await expect(filaPagada.getByText('PAGADA')).toBeVisible();
    });

    await test.step('la CxP quedó saldada (saldo 0 vía API) y el asiento cuadra si existe', async () => {
      const cxps = await sesion.api.get<{
        results?: Array<{ id_cxp: string; monto_pendiente: string; estado: string; observaciones: string | null }>;
      }>(`/cuentas-por-pagar/cuentas-por-pagar/?estado=PAGADA&proveedor=${proveedor.proveedorId}`);
      const lista = cxps.results ?? [];
      const cxp = lista.find((c) => (c.observaciones ?? '').includes(numeroOrden));
      expect(cxp, 'la CxP de la recepción debe existir y estar PAGADA').toBeTruthy();
      expect(cxp!.estado).toBe('PAGADA');
      expect(Number(cxp!.monto_pendiente)).toBe(0);

      // Asiento contable: opcional por empresa (ADR-006). Si la empresa generó
      // asientos aprobados, el balance de comprobación debe cuadrar (debe==haber).
      const balance = await sesion.api.get<{
        cuentas?: Array<{ debe: string; haber: string }>;
        total_debe?: string;
        total_haber?: string;
      }>(`/contabilidad/asientos-contables/balance_comprobacion/?empresa_id=${sesion.empresaId}`);
      if (balance.total_debe !== undefined && balance.total_haber !== undefined) {
        expect(Number(balance.total_debe)).toBeCloseTo(Number(balance.total_haber), 2);
      }
    });
  });
});
