import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cxcLubrikcaService', () => ({
  cxcLubrikcaService: {
    getResumen: vi.fn(),
    listPedidos: vi.fn(),
  },
}));

import { cxcLubrikcaService } from '../services/cxcLubrikcaService';
import CarteraPage from '../pages/CxcLubrikca/CarteraPage';

const resumen = {
  por_resultado: { verde: 0, amarillo: 0, rojo: 0 },
  total_conciliados: 0,
  total_facturados: 5,
  facturados_sin_conciliar: 2,
  pedidos_con_devolucion: 1,
  cartera_atascada: 1,
  bandejas_candidatas_sin_aprobar: 0,
  diferencia_total: '42.00',
};

const base = {
  cliente_externo_id: 'cli-1',
  vendedor_email: null,
  fecha: '2026-01-01',
  lista_precios: null,
  es_primera_compra: false,
  factura_id: null,
  monto_facturado: '0.00',
  entregada_completa: true,
};

const conDevolucion = {
  ...base,
  id: 'p1',
  so_id: 'SO-DEV-1',
  cliente_nombre: 'Cliente Devolución',
  monto_total: '200.00',
  fecha_entrega: '2026-06-01',
  facturada: true,
  estado_entrega: 'entregada',
  tiene_devolucion: true,
};

// No facturado con entrega vieja → cartera atascada (entrega en 2026-01-01).
const atascado = {
  ...base,
  id: 'p2',
  so_id: 'SO-ATASCADA-1',
  cliente_nombre: 'Cliente Atascado',
  monto_total: '350.00',
  fecha_entrega: '2026-01-01',
  facturada: false,
  estado_entrega: 'entregada',
  tiene_devolucion: false,
};

// Reciente, no facturado → NO atascado.
const reciente = {
  ...base,
  id: 'p3',
  so_id: 'SO-RECIENTE',
  cliente_nombre: 'Cliente Reciente',
  monto_total: '100.00',
  fecha_entrega: '2026-06-27',
  facturada: false,
  estado_entrega: 'entregada',
  tiene_devolucion: false,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <CarteraPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CarteraPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cxcLubrikcaService.getResumen).mockResolvedValue(resumen);
    vi.mocked(cxcLubrikcaService.listPedidos).mockResolvedValue([
      conDevolucion,
      atascado,
      reciente,
    ] as never);
  });

  afterEach(() => cleanup());

  it('muestra las KPIs de cartera del resumen', async () => {
    renderPage();
    expect(await screen.findByText('Cartera atascada')).toBeInTheDocument();
    expect(screen.getAllByText('Pedidos con devolución').length).toBeGreaterThan(0);
    expect(screen.getByText('Diferencia total')).toBeInTheDocument();
    // El valor se actualiza cuando resolve la query del resumen.
    expect(await screen.findByText(/42[.,]00/)).toBeInTheDocument();
  });

  it('lista solo los pedidos con devolución en su sección', async () => {
    renderPage();
    expect(await screen.findByText('SO-DEV-1')).toBeInTheDocument();
    expect(screen.getByText('Cliente Devolución')).toBeInTheDocument();
  });

  it('clasifica como atascado un pedido no facturado con entrega antigua', async () => {
    renderPage();
    expect(await screen.findByText('SO-ATASCADA-1')).toBeInTheDocument();
    // El pedido reciente no facturado NO debe aparecer (entrega < 30 días).
    expect(screen.queryByText('SO-RECIENTE')).not.toBeInTheDocument();
  });
});
