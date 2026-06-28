import { test, expect } from '@playwright/test';
import { iniciarSesion } from './helpers/sesion';
import { crearCliente, monedaUsd, sufijoUnico } from './helpers/datos';

/**
 * Flujo crítico — Fiscal: Libro de Ventas (compliance VE) cross-módulo.
 *
 * Cadena de punta a punta verificada:
 *   ventas (FacturaFiscal EMITIDA con IVA) → fiscal (Libro de Ventas SENIAT).
 *
 * El Libro de Ventas se ALIMENTA de `apps.ventas.FacturaFiscal`: el generador
 * SENIAT (`backend/apps/fiscal/libros_seniat.py::generar_libro_ventas_txt`)
 * filtra las facturas de la empresa por `fecha_emision` dentro del período y por
 * `estado in (EMITIDA, PAGADA, VENCIDA)`, y emite una línea pipe-delimited por
 * factura con BASE_IMPONIBLE|IVA|TOTAL. El endpoint
 * `GET /api/fiscal/libro-ventas/?empresa=<uuid>&periodo=YYYY-MM` devuelve ese TXT;
 * la página `/fiscal/libro-ventas` lo parsea y lo muestra como tabla con KPIs.
 *
 * Siembra: la FacturaFiscal se crea directamente vía API
 * (`POST /api/ventas/facturas-fiscales/`, EmpresaInjectMixin fija id_empresa),
 * lo cual es viable y determinista — no requiere recorrer pedido→nota→factura.
 *
 * Efecto cruzado verificado: la factura sembrada aparece en el Libro de Ventas
 * del período (UI), con su base imponible e IVA, y el KPI/total de IVA del libro
 * refleja exactamente el IVA de la factura (UI), además del cruce vía API (TXT).
 */

/** Período YYYY-MM de una fecha. */
function periodoDe(fecha: Date): string {
  return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, '0')}`;
}

interface FacturaFiscalApi {
  id_factura: string;
  numero_factura: string;
  numero_control: string;
  base_imponible: string;
  monto_iva: string;
  monto_total: string;
  estado: string;
}

test.describe('Fiscal: Libro de Ventas SENIAT (compliance VE)', () => {
  test('una FacturaFiscal con IVA aparece en el Libro de Ventas del período por UI y su IVA cuadra', async ({
    page,
  }) => {
    const sesion = await iniciarSesion(page);
    const suf = sufijoUnico();

    // Fecha de emisión = hoy → el período del libro es el mes en curso.
    const hoy = new Date();
    const fechaEmision = hoy.toISOString().slice(0, 10); // YYYY-MM-DD
    const periodo = periodoDe(hoy); // YYYY-MM (igual al default de la página)

    // Montos fiscales con IVA 16% (R-CODE-4: strings decimales).
    const baseImponible = '1000.00';
    const montoIva = '160.00';
    const montoTotal = '1160.00';

    // ── Prerequisitos sembrados vía API ──────────────────────────────────────
    const cliente = await crearCliente(sesion.api, sesion.empresaId, suf);
    const monedaUsdId = await monedaUsd(sesion.api);

    // Números cortos y únicos por corrida (unique_together por empresa).
    const numeroFactura = `FV${suf}`.slice(0, 20);
    const numeroControl = `NC${suf}`.slice(0, 20);

    let factura: FacturaFiscalApi | null = null;
    await test.step('sembrar una FacturaFiscal EMITIDA con IVA (API)', async () => {
      factura = await sesion.api.post<FacturaFiscalApi>('/ventas/facturas-fiscales/', {
        id_cliente: cliente.clienteId,
        numero_factura: numeroFactura,
        numero_control: numeroControl,
        fecha_emision: fechaEmision,
        base_imponible: baseImponible,
        monto_iva: montoIva,
        monto_igtf: '0.00',
        monto_total: montoTotal,
        id_moneda: monedaUsdId,
        tasa_cambio: '1.00',
        estado: 'EMITIDA',
      });
      expect(factura.estado).toBe('EMITIDA');
      expect(factura.numero_factura).toBe(numeroFactura);
    });

    await test.step('la factura aparece en el Libro de Ventas vía API (TXT SENIAT)', async () => {
      // Cruce backend directo: el generador SENIAT debe incluir la factura.
      // El endpoint LibroVentasView (APIView) solo tiene JSONRenderer registrado;
      // un `Accept: text/plain` hace que DRF rechace la negociación con 406. La
      // respuesta real es un HttpResponse text/plain crudo, así que pedimos `*/*`
      // (JSONRenderer satisface la negociación) y el cuerpo TXT llega igual.
      const txt = await page.request.get(
        `/api/fiscal/libro-ventas/?empresa=${sesion.empresaId}&periodo=${periodo}`,
        { headers: { Authorization: `Bearer ${sesion.api.access}`, Accept: '*/*' } },
      );
      expect(txt.ok(), `libro-ventas TXT → ${txt.status()}`).toBeTruthy();
      const cuerpo = await txt.text();
      // Cabecera SENIAT + al menos la línea de nuestra factura.
      expect(cuerpo).toContain('BASE_IMPONIBLE|IVA|TOTAL');
      expect(cuerpo).toContain(numeroFactura);
      expect(cuerpo).toContain(numeroControl);
      // La línea de la factura lleva base|iva|total con 2 decimales.
      expect(cuerpo).toContain(`${baseImponible}|${montoIva}|${montoTotal}`);
    });

    await test.step('el Libro de Ventas (UI) muestra la factura del período con base e IVA', async () => {
      await page.goto('/fiscal/libro-ventas');
      await expect(
        page.getByRole('heading', { name: 'Libro de Ventas — SENIAT' }),
      ).toBeVisible();

      // El selector de período arranca en el mes en curso (default de la página),
      // que coincide con el período de la factura; se consulta explícitamente.
      await page.getByRole('button', { name: 'Consultar' }).click();

      // La fila de la factura sembrada aparece con sus identificadores estables
      // (número de factura y de control). Los montos formateados dependen del
      // locale del navegador, así que se cruzan abajo con el formato que produce
      // la propia página (toLocaleString sin locale fijo → locale del runtime).
      const fila = page.getByRole('row').filter({ hasText: numeroFactura });
      await expect(fila).toBeVisible();
      await expect(fila.getByText(numeroControl)).toBeVisible();

      // Formato exacto que renderiza la página (fmt = toLocaleString por defecto),
      // evaluado en el MISMO runtime del navegador para no acoplarse a un locale.
      const baseFmt = await page.evaluate((n: number) =>
        n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        Number(baseImponible),
      );
      const ivaFmt = await page.evaluate((n: number) =>
        n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        Number(montoIva),
      );
      await expect(fila.getByText(baseFmt, { exact: true })).toBeVisible();
      await expect(fila.getByText(ivaFmt, { exact: true })).toBeVisible();
    });

    await test.step('el KPI de IVA del libro refleja el IVA de la factura (efecto cruzado)', async () => {
      // El KPI "IVA" suma el IVA de todas las facturas del período. Se valida con
      // el cruce API exacto (sumar el libro completo) para no acoplarse a otras
      // facturas que el seed/otras corridas hayan dejado en el mismo período.
      // `*/*` para que JSONRenderer satisfaga la negociación de DRF (ver paso
      // anterior): un `Accept: text/plain` devolvería 406.
      const txt = await page.request.get(
        `/api/fiscal/libro-ventas/?empresa=${sesion.empresaId}&periodo=${periodo}`,
        { headers: { Authorization: `Bearer ${sesion.api.access}`, Accept: '*/*' } },
      );
      const lineas = (await txt.text()).trim().split('\n').slice(1).filter(Boolean);
      const ivaTotalLibro = lineas.reduce((acc, l) => {
        const iva = l.split('|')[6] ?? '0';
        return acc + Number(iva);
      }, 0);
      // El total de IVA del libro incluye (≥) el IVA de la factura sembrada.
      expect(ivaTotalLibro).toBeGreaterThanOrEqual(Number(montoIva));

      // Y la UI muestra ese mismo total de IVA en el KPI (formato del runtime).
      const ivaUi = await page.evaluate((n: number) =>
        n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        ivaTotalLibro,
      );
      await expect(page.getByText(ivaUi).first()).toBeVisible();
    });
  });
});
