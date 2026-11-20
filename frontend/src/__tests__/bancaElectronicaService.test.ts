import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  fetchBlob: vi.fn(),
}));

import { del, fetchBlob, get, patch, post } from '../services/api';
import {
  cuentasBancariasEmpresaService,
  lotesPagoBancarioService,
  validarCuentaVe,
  validarReferenciaBancaria,
  type CuentaBancariaEmpresaPayload,
} from '../services/bancaElectronicaService';

const CUENTAS_BASE = '/finanzas/cuentas-bancarias-empresa/';
const LOTES_BASE = '/banca-electronica/lotes-pago/';

const payload: CuentaBancariaEmpresaPayload = {
  id_empresa: 'e1',
  nombre_banco: 'Banco de Venezuela',
  numero_cuenta: '0102-1234-5678-9012',
  tipo_cuenta: 'CORRIENTE',
  id_moneda: 'mon-1',
  saldo_actual: '1500.00',
  activo: true,
};

describe('cuentasBancariasEmpresaService CRUD (finanzas canónico)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma el querystring con empresa (respuesta paginada)', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_cuenta_bancaria: 'c1' }] });
    const r = await cuentasBancariasEmpresaService.getAll({ empresa: 'e1' });
    expect(get).toHaveBeenCalledWith(`${CUENTAS_BASE}?empresa=e1`);
    expect(r).toEqual([{ id_cuenta_bancaria: 'c1' }]);
  });

  it('getAll sin parámetros pega al endpoint base (respuesta array)', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_cuenta_bancaria: 'c1' }]);
    const r = await cuentasBancariasEmpresaService.getAll();
    expect(get).toHaveBeenCalledWith(CUENTAS_BASE);
    expect(r).toEqual([{ id_cuenta_bancaria: 'c1' }]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_cuenta_bancaria: 'c1' });
    await cuentasBancariasEmpresaService.getById('c1');
    expect(get).toHaveBeenCalledWith(`${CUENTAS_BASE}c1/`);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_cuenta_bancaria: 'c2' });
    await cuentasBancariasEmpresaService.create(payload);
    expect(post).toHaveBeenCalledWith(CUENTAS_BASE, payload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_cuenta_bancaria: 'c2' });
    await cuentasBancariasEmpresaService.update('c2', payload);
    expect(patch).toHaveBeenCalledWith(`${CUENTAS_BASE}c2/`, payload);
  });

  it('remove borra por id', async () => {
    vi.mocked(del).mockResolvedValue(undefined);
    await cuentasBancariasEmpresaService.remove('c2');
    expect(del).toHaveBeenCalledWith(`${CUENTAS_BASE}c2/`);
  });
});

describe('lotesPagoBancarioService y validadores VE', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll arma filtros de empresa, tipo_lote y estado', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_lote_pago: 'l1' }] });
    const res = await lotesPagoBancarioService.getAll({
      empresa: 'e1',
      tipo_lote: 'PROVEEDORES',
      estado: 'GENERADO',
    });
    expect(get).toHaveBeenCalledWith(`${LOTES_BASE}?empresa=e1&tipo_lote=PROVEEDORES&estado=GENERADO`);
    expect(res).toEqual([{ id_lote_pago: 'l1' }]);
  });

  it('generarProveedores y generarNomina invocan endpoints atómicos', async () => {
    vi.mocked(post).mockResolvedValue({ id_lote_pago: 'l1' });
    await lotesPagoBancarioService.generarProveedores({
      id_cuenta_bancaria: 'c1',
      pagos_ids: ['p1'],
      formato_banco: 'BANESCO_TXT',
      fecha_valor: '2026-11-20',
    });
    expect(post).toHaveBeenCalledWith(`${LOTES_BASE}generar-proveedores/`, {
      id_cuenta_bancaria: 'c1',
      pagos_ids: ['p1'],
      formato_banco: 'BANESCO_TXT',
      fecha_valor: '2026-11-20',
    });

    await lotesPagoBancarioService.generarNomina({
      id_cuenta_bancaria: 'c1',
      id_proceso_nomina: 'proc-1',
      formato_banco: 'MERCANTIL_TXT',
      fecha_valor: '2026-11-20',
    });
    expect(post).toHaveBeenCalledWith(`${LOTES_BASE}generar-nomina/`, {
      id_cuenta_bancaria: 'c1',
      id_proceso_nomina: 'proc-1',
      formato_banco: 'MERCANTIL_TXT',
      fecha_valor: '2026-11-20',
    });
  });

  it('descargar solicita blob con Accept */* y transiciones postean acción', async () => {
    const blob = new Blob(['01|BANESCO'], { type: 'text/plain' });
    vi.mocked(fetchBlob).mockResolvedValueOnce(blob);
    const out = await lotesPagoBancarioService.descargar('l1');
    expect(fetchBlob).toHaveBeenCalledWith(`${LOTES_BASE}l1/descargar/`, {
      headers: { Accept: '*/*' },
    });
    expect(out).toBe(blob);

    vi.mocked(post).mockResolvedValue({ id_lote_pago: 'l1' });
    await lotesPagoBancarioService.marcarEnviado('l1');
    expect(post).toHaveBeenCalledWith(`${LOTES_BASE}l1/marcar-enviado/`, {});
    await lotesPagoBancarioService.marcarProcesado('l1');
    expect(post).toHaveBeenCalledWith(`${LOTES_BASE}l1/marcar-procesado/`, {});
    await lotesPagoBancarioService.anular('l1');
    expect(post).toHaveBeenCalledWith(`${LOTES_BASE}l1/anular/`, {});
  });

  it('validarCuentaVe y validarReferenciaBancaria invocan sus endpoints', async () => {
    vi.mocked(post).mockResolvedValueOnce({ valida: true, banco_nombre: 'Banesco' });
    await validarCuentaVe('0134-0001-01-0123456789');
    expect(post).toHaveBeenCalledWith('/banca-electronica/validar-cuenta-ve/', {
      numero_cuenta: '0134-0001-01-0123456789',
    });

    vi.mocked(post).mockResolvedValueOnce({ duplicada: true, referencia_normalizada: 'REF-1' });
    await validarReferenciaBancaria({ referencia: 'REF-1', id_cuenta_bancaria: 'c1' });
    expect(post).toHaveBeenCalledWith('/banca-electronica/validar-referencia/', {
      referencia: 'REF-1',
      id_cuenta_bancaria: 'c1',
    });
  });
});
