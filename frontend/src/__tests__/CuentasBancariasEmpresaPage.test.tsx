import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  fetchBlob: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));
vi.mock('../services/monedas', () => ({ fetchMonedas: vi.fn() }));

import { del, fetchBlob, get, patch, post } from '../services/api';
import { fetchMonedas } from '../services/monedas';
import CuentasBancariasEmpresaPage from '../pages/BancaElectronica/CuentasBancariasEmpresaPage';

const cuentaApi = {
  id_cuenta_bancaria: 'cta-1',
  id_empresa: 'e1',
  nombre_banco: 'Banco de Venezuela',
  numero_cuenta: '0102-0001',
  tipo_cuenta: 'CORRIENTE',
  id_moneda: 'mon-1',
  moneda_codigo_iso: 'USD',
  saldo_actual: '1500.00',
  activo: true,
};

const loteApi = {
  id_lote_pago: 'lote-1',
  id_empresa: 'e1',
  empresa_nombre: 'Empresa 1',
  id_cuenta_bancaria: 'cta-1',
  cuenta_bancaria_nombre: 'Banco de Venezuela',
  cuenta_bancaria_numero: '0102-0001',
  tipo_lote: 'PROVEEDORES',
  formato_banco: 'BANESCO_TXT',
  referencia_lote: 'LOTE-PROV-001',
  fecha_valor: '2026-11-20',
  estado: 'GENERADO',
  id_proceso_nomina: null,
  total_registros: 1,
  monto_total: '250.50',
  sha256_archivo: 'abc123',
  nombre_archivo: 'lote_banesco.txt',
  generado_por: 'user-1',
  activo: true,
  fecha_creacion: '2026-11-20T12:00:00Z',
  fecha_actualizacion: '2026-11-20T12:00:00Z',
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CuentasBancariasEmpresaPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CuentasBancariasEmpresaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/finanzas/cuentas-bancarias-empresa')) {
        return Promise.resolve([cuentaApi]);
      }
      if (url.startsWith('/banca-electronica/lotes-pago')) {
        return Promise.resolve([loteApi]);
      }
      if (url.startsWith('/finanzas/pagos')) {
        return Promise.resolve([
          {
            id_pago: 'pago-1',
            tipo_operacion: 'EGRESO',
            referencia: 'PAG-001',
            monto: '250.50',
            moneda_codigo: 'USD',
          },
          {
            id_pago: 'pago-ing',
            tipo_operacion: 'INGRESO',
            referencia: 'ING-SKIP',
            monto: '100.00',
            moneda_codigo: 'USD',
          },
        ]);
      }
      if (url.startsWith('/nomina/procesos-nomina')) {
        return Promise.resolve([
          {
            id_proceso_nomina: 'proc-1',
            numero_proceso: 'NOM-001',
            estado: 'APROBADO',
            total_neto: '1000.00',
          },
        ]);
      }
      return Promise.resolve([]);
    });
    vi.mocked(fetchMonedas).mockResolvedValue([
      { id_moneda: 'mon-1', nombre: 'Dólar', codigo_iso: 'USD' },
    ]);
  });

  it('lista las cuentas canónicas con banco, número, tipo, moneda y saldo', async () => {
    renderPage();
    expect(await screen.findByText('Banco de Venezuela')).toBeInTheDocument();
    expect(screen.getByText('0102-0001')).toBeInTheDocument();
    expect(screen.getByText('Corriente')).toBeInTheDocument();
    expect(screen.getByText('USD')).toBeInTheDocument();
    expect(screen.getByText('1500.00')).toBeInTheDocument();
  });

  it('valida campos requeridos y formato decimal estricto al crear', async () => {
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    expect(await screen.findByText('Nueva cuenta', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Complete el banco, el número de cuenta y la moneda/),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Banco/), { target: { value: 'Banesco' } });
    fireEvent.change(screen.getByLabelText(/Número de cuenta/), { target: { value: '0134-1' } });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
    fireEvent.change(screen.getByLabelText(/Saldo actual/), { target: { value: 'abc' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/número decimal válido/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una cuenta contra /finanzas/cuentas-bancarias-empresa/', async () => {
    vi.mocked(post).mockResolvedValue({ id_cuenta_bancaria: 'cta-2' });
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('button', { name: 'Nueva cuenta' }));
    fireEvent.change(await screen.findByLabelText(/Banco/), { target: { value: 'Banesco' } });
    fireEvent.change(screen.getByLabelText(/Número de cuenta/), { target: { value: '0134-9999' } });
    fireEvent.mouseDown(screen.getByLabelText(/Moneda/));
    fireEvent.click(await screen.findByRole('option', { name: /USD — Dólar/ }));
    fireEvent.change(screen.getByLabelText(/Saldo actual/), { target: { value: '250.50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/finanzas/cuentas-bancarias-empresa/',
        expect.objectContaining({
          id_empresa: 'e1',
          nombre_banco: 'Banesco',
          numero_cuenta: '0134-9999',
          tipo_cuenta: 'CORRIENTE',
          id_moneda: 'mon-1',
          saldo_actual: '250.50',
          activo: true,
        }),
      ),
    );
  });

  it('edita una cuenta canónica', async () => {
    vi.mocked(patch).mockResolvedValue({ id_cuenta_bancaria: 'cta-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const banco = (await screen.findByLabelText(/Banco/)) as HTMLInputElement;
    await waitFor(() => expect(banco.value).toBe('Banco de Venezuela'));
    fireEvent.change(banco, { target: { value: 'BdV Editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/finanzas/cuentas-bancarias-empresa/cta-1/',
        expect.objectContaining({ nombre_banco: 'BdV Editado', id_empresa: 'e1' }),
      ),
    );
  });

  it('elimina una cuenta canónica tras confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/finanzas/cuentas-bancarias-empresa/cta-1/'),
    );
    confirmSpy.mockRestore();
  });

  it('genera lote de proveedores desde el diálogo en Lotes de Pago VE', async () => {
    vi.mocked(post).mockResolvedValue({ ...loteApi, referencia_lote: 'LOTE-PROV-NEW' });
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('tab', { name: 'Lotes de Pago VE' }));
    await screen.findByText('LOTE-PROV-001');

    fireEvent.click(screen.getByRole('button', { name: 'Generar Lote Proveedores' }));
    expect(await screen.findByText('Generar Lote de Pago a Proveedores')).toBeInTheDocument();
    const pagoCheckbox = await screen.findByLabelText(/PAG-001/);
    expect(screen.queryByLabelText(/ING-SKIP/)).not.toBeInTheDocument();
    fireEvent.click(pagoCheckbox);
    fireEvent.click(screen.getByRole('button', { name: 'Generar Lote' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/banca-electronica/lotes-pago/generar-proveedores/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_cuenta_bancaria: 'cta-1',
          pagos_ids: ['pago-1'],
          formato_banco: 'BANESCO_TXT',
        }),
      ),
    );
  });

  it('genera lote de nómina desde el diálogo en Lotes de Pago VE', async () => {
    vi.mocked(post).mockResolvedValue({ ...loteApi, tipo_lote: 'NOMINA', referencia_lote: 'LOTE-NOM-NEW' });
    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('tab', { name: 'Lotes de Pago VE' }));
    await screen.findByText('LOTE-PROV-001');

    fireEvent.click(screen.getByRole('button', { name: 'Generar Lote Nómina' }));
    expect(await screen.findByText('Generar Lote de Pago de Nómina')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByLabelText(/Proceso de nómina/));
    fireEvent.click(await screen.findByRole('option', { name: /NOM-001/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Generar Lote' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/banca-electronica/lotes-pago/generar-nomina/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_cuenta_bancaria: 'cta-1',
          id_proceso_nomina: 'proc-1',
          formato_banco: 'BANESCO_TXT',
        }),
      ),
    );
  });

  it('pestaña Lotes de Pago VE lista, transiciona y descarga lotes', async () => {
    vi.mocked(post).mockResolvedValue({ ...loteApi, estado: 'ENVIADO' });
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => 'blob:mock');
    URL.revokeObjectURL = vi.fn();
    vi.mocked(fetchBlob).mockResolvedValue(new Blob(['contenido']));

    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('tab', { name: 'Lotes de Pago VE' }));

    expect(await screen.findByText('LOTE-PROV-001')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/banca-electronica/lotes-pago/lote-1/marcar-enviado/', {}),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Descargar' }));
    await waitFor(() =>
      expect(fetchBlob).toHaveBeenCalledWith('/banca-electronica/lotes-pago/lote-1/descargar/', {
        headers: { Accept: '*/*' },
      }),
    );

    URL.createObjectURL = origCreate;
    URL.revokeObjectURL = origRevoke;
  });

  it('pestaña Validador Bancario valida cuenta VE y referencia duplicada', async () => {
    vi.mocked(post)
      .mockResolvedValueOnce({
        valida: true,
        numero_normalizado: '01340001010123456789',
        codigo_banco: '0134',
        banco_nombre: 'Banesco',
        errores: [],
      })
      .mockResolvedValueOnce({
        duplicada: true,
        referencia_normalizada: 'REF-100',
        coincidencias: [{ origen: 'finanzas.Pago', id: 'p1', detalle: 'Pago ref=REF-100' }],
      });

    renderPage();
    await screen.findByText('Banco de Venezuela');
    fireEvent.click(screen.getByRole('tab', { name: 'Validador Bancario' }));

    fireEvent.change(await screen.findByLabelText(/Número de cuenta VE/), {
      target: { value: '0134-0001-01-0123456789' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Validar Cuenta VE' }));
    expect(await screen.findByText(/Cuenta válida · Banesco/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Referencia bancaria/), {
      target: { value: 'ref-100' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Verificar Referencia' }));
    expect(await screen.findByText(/Referencia REF-100 duplicada/)).toBeInTheDocument();
  });
});
