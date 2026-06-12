import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/tesoreriaService', () => ({
  tesoreriaService: {
    getConciliacionesPaginated: vi.fn(),
    getConciliacion: vi.fn(),
    getCuentasBancarias: vi.fn(),
    crearConciliacion: vi.fn(),
    cerrarConciliacion: vi.fn(),
    conciliarAuto: vi.fn(),
    getMovimientosBancariosPaginated: vi.fn(),
  },
}));

import { tesoreriaService } from '../services/tesoreriaService';
import ConciliacionesListPage from '../pages/Tesoreria/ConciliacionesListPage';
import ConciliacionDetailPage from '../pages/Tesoreria/ConciliacionDetailPage';

const cuenta = {
  id_cuenta_bancaria: 'cb-1',
  nombre_banco: 'Banco Uno',
  numero_cuenta: '0102-0001',
  activo: true,
};

const conciliacion = {
  id: 'con-1',
  id_empresa: 'emp-1',
  id_cuenta_bancaria: 'cb-1',
  periodo_inicio: '2026-06-01',
  periodo_fin: '2026-06-30',
  saldo_banco: '1000.30',
  saldo_libro: '1000.10',
  diferencia: '0.20',
  estado: 'ABIERTA',
  movimientos_conciliados: 3,
  movimientos_pendientes: 2,
  realizada_por: null,
  fecha_creacion: '2026-06-11T10:00:00Z',
  fecha_cierre: null,
  observaciones: 'Cierre de junio',
};

const movimiento = {
  id: 'mov-1',
  id_empresa: 'emp-1',
  id_cuenta_bancaria: 'cb-1',
  fecha_mov: '2026-06-10',
  descripcion: 'Pago cliente ACME',
  tipo: 'CREDITO',
  monto: '500.00',
  referencia: '',
  estado: 'PENDIENTE',
  id_pago_conciliado: null,
  origen: 'MANUAL',
  fecha_creacion: '2026-06-10T10:00:00Z',
};

function renderList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/tesoreria/conciliaciones']}>
          <Routes>
            <Route path="/tesoreria/conciliaciones" element={<ConciliacionesListPage />} />
            <Route path="/tesoreria/conciliaciones/:id" element={<div>DETALLE-CONCILIACION</div>} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function renderDetail() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/tesoreria/conciliaciones/con-1']}>
          <Routes>
            <Route path="/tesoreria/conciliaciones/:id" element={<ConciliacionDetailPage />} />
          </Routes>
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('ConciliacionesListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(tesoreriaService.getConciliacionesPaginated).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [conciliacion],
    });
    vi.mocked(tesoreriaService.getCuentasBancarias).mockResolvedValue([cuenta]);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('lista las conciliaciones con saldos y diferencia decimal exacta', async () => {
    renderList();
    expect(await screen.findByText('2026-06-01 → 2026-06-30')).toBeInTheDocument();
    expect(screen.getByText('1000.30')).toBeInTheDocument();
    expect(screen.getByText('1000.10')).toBeInTheDocument();
    expect(screen.getByText('0.20')).toBeInTheDocument();
    expect(screen.getByText('ABIERTA')).toBeInTheDocument();
  });

  it('crea una sesión y navega al detalle; la diferencia se previsualiza con decimal.js', async () => {
    vi.mocked(tesoreriaService.crearConciliacion).mockResolvedValue(conciliacion);
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ABIERTA');

    await user.click(screen.getByRole('button', { name: 'Nueva conciliación' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText(/Cuenta bancaria/));
    await user.click(await screen.findByRole('option', { name: /Banco Uno — 0102-0001/ }));
    await user.type(within(dialog).getByLabelText(/Saldo banco/), '0.30');
    await user.type(within(dialog).getByLabelText(/Saldo libros/), '0.10');
    // 0.30 − 0.10 = 0.20 exacto: con float sería 0.19999999999999998.
    expect(within(dialog).getByText(/Diferencia banco − libros: 0\.20/)).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(tesoreriaService.crearConciliacion).toHaveBeenCalledWith(
        expect.objectContaining({
          id_empresa: 'emp-1',
          id_cuenta_bancaria: 'cb-1',
          saldo_banco: '0.30',
          saldo_libro: '0.10',
        }),
      );
    });
    expect(await screen.findByText('DETALLE-CONCILIACION')).toBeInTheDocument();
  });

  it('muestra el error del backend al crear', async () => {
    vi.mocked(tesoreriaService.crearConciliacion).mockRejectedValue(
      new Error(JSON.stringify({ error: 'Ya existe una conciliación abierta.' })),
    );
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ABIERTA');

    await user.click(screen.getByRole('button', { name: 'Nueva conciliación' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText(/Cuenta bancaria/));
    await user.click(await screen.findByRole('option', { name: /Banco Uno — 0102-0001/ }));
    await user.type(within(dialog).getByLabelText(/Saldo banco/), '1');
    await user.type(within(dialog).getByLabelText(/Saldo libros/), '1');
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }));

    expect(await screen.findByText(/Ya existe una conciliación abierta\./)).toBeInTheDocument();
  });
});

describe('ConciliacionDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tesoreriaService.getConciliacion).mockResolvedValue(conciliacion);
    vi.mocked(tesoreriaService.getMovimientosBancariosPaginated).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [movimiento],
    });
  });

  afterEach(() => cleanup());

  it('muestra saldos, diferencia y movimientos de la cuenta', async () => {
    renderDetail();
    expect(await screen.findByText('Detalle de Conciliación')).toBeInTheDocument();
    expect(screen.getByText('1000.30')).toBeInTheDocument();
    expect(screen.getByText('1000.10')).toBeInTheDocument();
    expect(screen.getByText('0.20')).toBeInTheDocument();
    expect(await screen.findByText('Pago cliente ACME')).toBeInTheDocument();
    expect(screen.getByText('Cierre de junio')).toBeInTheDocument();
  });

  it('ejecuta el matching automático (conciliar-auto) sobre la cuenta', async () => {
    vi.mocked(tesoreriaService.conciliarAuto).mockResolvedValue({ conciliados: 2, pendientes: 1 });
    const user = userEvent.setup();
    renderDetail();
    await screen.findByText('Detalle de Conciliación');

    await user.click(screen.getByRole('button', { name: 'Conciliar automático' }));
    await waitFor(() => {
      expect(tesoreriaService.conciliarAuto).toHaveBeenCalledWith('cb-1');
    });
  });

  it('cierra la conciliación', async () => {
    vi.mocked(tesoreriaService.cerrarConciliacion).mockResolvedValue({
      ...conciliacion,
      estado: 'CERRADA',
    });
    const user = userEvent.setup();
    renderDetail();
    await screen.findByText('Detalle de Conciliación');

    await user.click(screen.getByRole('button', { name: 'Cerrar conciliación' }));
    await waitFor(() => {
      expect(tesoreriaService.cerrarConciliacion).toHaveBeenCalledWith('con-1');
    });
  });

  it('oculta las acciones cuando la conciliación está CERRADA', async () => {
    vi.mocked(tesoreriaService.getConciliacion).mockResolvedValue({
      ...conciliacion,
      estado: 'CERRADA',
    });
    renderDetail();
    await screen.findByText('Detalle de Conciliación');
    expect(screen.queryByRole('button', { name: 'Conciliar automático' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cerrar conciliación' })).not.toBeInTheDocument();
  });
});
