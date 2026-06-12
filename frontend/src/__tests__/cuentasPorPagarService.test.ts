import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  fetcher: vi.fn(),
}));

import { get, fetcher } from '../services/api';
import { cuentasPorPagarService } from '../services/cuentasPorPagarService';

const cxp = {
  id_cxp: 'cxp-1',
  id_empresa: 'emp-1',
  id_proveedor: 'prov-1',
  id_factura_compra: 'fac-1',
  referencia_externa: 'FAC-001',
  monto_total: '255.0000',
  monto_pendiente: '100.0000',
  fecha_emision: '2026-06-01',
  fecha_vencimiento: '2026-07-01',
  estado: 'PARCIAL',
  observaciones: null,
  activo: true,
  fecha_creacion: '2026-06-01T10:00:00Z',
};

describe('cuentasPorPagarService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getAllPaginated pasa page/page_size y devuelve la página DRF', async () => {
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [cxp] });
    const res = await cuentasPorPagarService.getAllPaginated(2, 10);
    expect(get).toHaveBeenCalledWith('/cuentas-por-pagar/cuentas-por-pagar/?page=2&page_size=10');
    expect(res.results[0].monto_pendiente).toBe('100.0000');
  });

  it('getAllPaginated agrega los filtros de estado y proveedor', async () => {
    vi.mocked(get).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    await cuentasPorPagarService.getAllPaginated(1, 20, { estado: 'VENCIDA', proveedor: 'prov-1' });
    expect(get).toHaveBeenCalledWith(
      '/cuentas-por-pagar/cuentas-por-pagar/?page=1&page_size=20&estado=VENCIDA&proveedor=prov-1',
    );
  });

  it('getAllPaginated normaliza listas directas', async () => {
    vi.mocked(get).mockResolvedValue([cxp]);
    const res = await cuentasPorPagarService.getAllPaginated();
    expect(res).toEqual({ count: 1, next: null, previous: null, results: [cxp] });
  });

  it('getAging consulta el aging con la empresa', async () => {
    const aging = {
      empresa_id: 'emp-1',
      corriente: { monto: '50.00', cantidad: 1 },
      dias_1_30: { monto: '0', cantidad: 0 },
      dias_31_60: { monto: '0', cantidad: 0 },
      dias_61_90: { monto: '0', cantidad: 0 },
      dias_90_mas: { monto: '50.00', cantidad: 2 },
      total_general: '100.00',
    };
    vi.mocked(get).mockResolvedValue(aging);
    const res = await cuentasPorPagarService.getAging('emp-1');
    expect(get).toHaveBeenCalledWith('/cuentas-por-pagar/cuentas-por-pagar/aging/?empresa=emp-1');
    expect(res.total_general).toBe('100.00');
  });

  it('abonar envía la cabecera Idempotency-Key y el monto como string', async () => {
    vi.mocked(fetcher).mockResolvedValue({
      abono_id: 'ab-1',
      cxp_id: 'cxp-1',
      monto_abonado: '50.00',
      monto_pendiente: '50.0000',
      estado_cxp: 'PARCIAL',
    });
    const res = await cuentasPorPagarService.abonar(
      'cxp-1',
      { monto: '50.00', descripcion: 'Pago parcial' },
      'clave-uuid-1',
    );
    expect(fetcher).toHaveBeenCalledWith('/cuentas-por-pagar/cuentas-por-pagar/cxp-1/abonar/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': 'clave-uuid-1',
      },
      body: JSON.stringify({ monto: '50.00', descripcion: 'Pago parcial' }),
    });
    expect(res.monto_pendiente).toBe('50.0000');
  });
});
