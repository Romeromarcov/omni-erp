import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  API_URL: 'http://localhost:8000/api',
}));

import { get, post } from '../services/api';
import {
  clearPortalClienteSession,
  getPortalClienteSession,
  portalClienteService,
  portalConductorService,
  portalVendedorService,
  safeExternalUrl,
  setPortalClienteSession,
} from '../services/portalesService';

describe('safeExternalUrl', () => {
  it('acepta http/https y resuelve rutas relativas /api/', () => {
    expect(safeExternalUrl('https://waze.com/ul?ll=10,-66&navigate=yes')).toBe(
      'https://waze.com/ul?ll=10,-66&navigate=yes',
    );
    expect(safeExternalUrl('http://localhost:8000/api/ventas/facturas/1/pdf/')).toBe(
      'http://localhost:8000/api/ventas/facturas/1/pdf/',
    );
    expect(safeExternalUrl('/api/ventas/facturas-fiscales/f1/pdf/')).toBe(
      'http://localhost:8000/api/ventas/facturas-fiscales/f1/pdf/',
    );
  });

  it('rechaza javascript:, data:, vacíos y caracteres de control', () => {
    expect(safeExternalUrl(null)).toBeUndefined();
    expect(safeExternalUrl('')).toBeUndefined();
    expect(safeExternalUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeExternalUrl('data:text/html,<script>')).toBeUndefined();
    expect(safeExternalUrl('https://ok.test/\ninjected')).toBeUndefined();
  });
});

describe('sessionStorage PortalClienteSession', () => {
  beforeEach(() => {
    clearPortalClienteSession();
  });

  it('guarda, lee y limpia sesión del portal cliente', () => {
    expect(getPortalClienteSession()).toBeNull();
    const sess = {
      session_token: 'tok-abc',
      expira_en: '2026-11-25T12:00:00Z',
      cliente: {
        id_cliente: 'c1',
        razon_social: 'Cliente Uno CA',
        rif: 'J-12345678',
        empresa_id: 'e1',
        empresa_nombre: 'Empresa Alpha',
      },
    };
    setPortalClienteSession(sess);
    expect(getPortalClienteSession()).toEqual(sess);
    clearPortalClienteSession();
    expect(getPortalClienteSession()).toBeNull();
  });

  it('devuelve null ante JSON corrupto en sessionStorage', () => {
    window.sessionStorage.setItem('omni_portal_cliente_session_v1', '{bad json');
    expect(getPortalClienteSession()).toBeNull();
  });
});

describe('portalVendedorService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('consulta cartera, catálogo trimonetario y metas', async () => {
    vi.mocked(get).mockResolvedValue({ empresa_id: 'e1', clientes: [] });
    await portalVendedorService.getCartera('e1', true);
    expect(get).toHaveBeenCalledWith('/ventas/portal-vendedor/cartera/?empresa=e1&todos=1');

    await portalVendedorService.getCatalogo('aceite', 'e1');
    expect(get).toHaveBeenCalledWith('/ventas/portal-vendedor/catalogo/?q=aceite&empresa=e1');

    await portalVendedorService.getMetasComisiones();
    expect(get).toHaveBeenCalledWith('/ventas/portal-vendedor/metas-comisiones/');
  });

  it('envía check-in, pedidos y cobros con Idempotency-Key', async () => {
    vi.mocked(post).mockResolvedValue({});
    await portalVendedorService.registrarCheckin({
      id_cliente: 'c1',
      latitud: '10.48',
      longitud: '-66.85',
    });
    expect(post).toHaveBeenLastCalledWith(
      '/ventas/portal-vendedor/checkin/',
      expect.objectContaining({ id_cliente: 'c1' }),
      expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }),
    );

    await portalVendedorService.crearPedido({
      id_cliente: 'c1',
      lineas: [{ id_producto: 'p1', cantidad: '2' }],
    });
    expect(post).toHaveBeenLastCalledWith(
      '/ventas/portal-vendedor/pedidos/',
      expect.objectContaining({ id_cliente: 'c1' }),
      expect.any(Object),
    );

    await portalVendedorService.reportarCobro({
      id_cliente: 'c1',
      monto: '25.00',
      id_moneda: 'm1',
      id_metodo_pago: 'mp1',
    });
    expect(post).toHaveBeenLastCalledWith(
      '/ventas/portal-vendedor/cobros/',
      expect.objectContaining({ monto: '25.00' }),
      expect.any(Object),
    );
  });

  it('normaliza catálogos paginados o en lista plana', async () => {
    vi.mocked(get)
      .mockResolvedValueOnce({ results: [{ id_moneda: 'm1', codigo_iso: 'USD', nombre: 'Dólar', simbolo: '$' }] })
      .mockResolvedValueOnce([{ id_metodo_pago: 'mp1', nombre_metodo: 'Zelle', tipo_metodo: 'TRANSFERENCIA' }]);

    const monedas = await portalVendedorService.getMonedasCatalogo();
    const metodos = await portalVendedorService.getMetodosPagoCatalogo();
    expect(monedas).toHaveLength(1);
    expect(metodos).toHaveLength(1);
  });
});

describe('portalClienteService', () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('ejecuta flujo OTP, resumen, pago idempotente, pedido y tracking con X-Portal-Cliente-Token', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });

    await portalClienteService.solicitarOtp({ rif: 'J-12345678', canal: 'WHATSAPP' });
    await portalClienteService.verificarOtp({ rif: 'J-12345678', codigo: '123456' });
    await portalClienteService.getResumen('sess-tok');
    await portalClienteService.reportarPago('sess-tok', {
      monto: '50.00',
      id_moneda: 'm1',
      id_metodo_pago: 'mp1',
    });
    await portalClienteService.crearPedido('sess-tok', {
      lineas: [{ id_producto: 'p1', cantidad: '1' }],
    });
    await portalClienteService.getTracking('sess-tok');

    expect(fetchSpy).toHaveBeenCalledTimes(6);
    const pagoCallHeaders = fetchSpy.mock.calls[3][1].headers;
    expect(pagoCallHeaders['X-Portal-Cliente-Token']).toBe('sess-tok');
    expect(pagoCallHeaders['Idempotency-Key']).toBeTruthy();
  });

  it('propaga errores HTTP leyendo detail/error/campos de validación', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Código OTP incorrecto.' }),
    });
    await expect(portalClienteService.verificarOtp({ rif: 'J-1', codigo: '000000' })).rejects.toThrow(
      'Código OTP incorrecto.',
    );

    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ monto: ['Debe ser positivo.'] }),
    });
    await expect(
      portalClienteService.reportarPago('tok', { monto: '-1', id_moneda: 'm1', id_metodo_pago: 'mp1' }),
    ).rejects.toThrow('Debe ser positivo.');
  });
});

describe('portalConductorService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('consulta rutas y ejecuta escanear-bulto y epod con Idempotency-Key', async () => {
    vi.mocked(get).mockResolvedValue({ empresa_id: 'e1', rutas: [] });
    vi.mocked(post).mockResolvedValue({ ok: true });

    await portalConductorService.getMisRutas({ conductor: 'c1', empresa: 'e1' });
    expect(get).toHaveBeenCalledWith('/despacho/portal-conductor/mis-rutas/?conductor=c1&empresa=e1');

    await portalConductorService.escanearBulto('par-1', { codigo_bulto: 'SKU-1' });
    expect(post).toHaveBeenLastCalledWith(
      '/despacho/portal-conductor/paradas/par-1/escanear-bulto/',
      { codigo_bulto: 'SKU-1' },
      expect.any(Object),
    );

    await portalConductorService.registrarEpod('par-1', {
      resultado: 'ENTREGADA',
      receptor_nombre: 'Ana Pérez',
    });
    expect(post).toHaveBeenLastCalledWith(
      '/despacho/portal-conductor/paradas/par-1/epod/',
      { resultado: 'ENTREGADA', receptor_nombre: 'Ana Pérez' },
      expect.any(Object),
    );
  });
});
