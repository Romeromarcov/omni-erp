import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cxcLubrikcaService', () => ({
  cxcLubrikcaService: {
    listBandeja: vi.fn(),
    proponerCierre: vi.fn(),
    confirmarCierre: vi.fn(),
  },
}));

import { cxcLubrikcaService } from '../services/cxcLubrikcaService';
import BandejaPage from '../pages/CxcLubrikca/BandejaPage';

const bandeja = {
  id: 'b1',
  pedido: 'SO-0001',
  lista_aplicada: 'Mayorista',
  precio_base_calculado: '500.00',
  descuentos_detalle: {},
  total_descuentos: '20.00',
  ncs_calculadas: '0.00',
  total_motor: '480.00',
  requiere_revision: false,
  candidata_a_cierre: true,
  estado: 'calculado',
  aprobado_por: null,
  calculado_en: '2026-06-05T10:00:00Z',
};

const bandejaNoCandidata = {
  ...bandeja,
  id: 'b2',
  pedido: 'SO-0002',
  candidata_a_cierre: false,
  estado: 'borrador',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <BandejaPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('BandejaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cxcLubrikcaService.listBandeja).mockResolvedValue([bandeja, bandejaNoCandidata] as never);
  });

  afterEach(() => cleanup());

  it('lista las bandejas con su total motor', async () => {
    renderPage();
    expect(await screen.findByText('SO-0001')).toBeInTheDocument();
    expect(screen.getByText('SO-0002')).toBeInTheDocument();
    expect(screen.getAllByText('Mayorista').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/480,00/).length).toBeGreaterThan(0);
  });

  it('deshabilita "Proponer cierre" si no es candidata o no está calculada', async () => {
    renderPage();
    await screen.findByText('SO-0001');
    const botones = screen.getAllByRole('button', { name: /proponer cierre/i });
    expect(botones[0]).toBeEnabled();
    expect(botones[1]).toBeDisabled();
  });

  it('propone el cierre de una bandeja candidata', async () => {
    vi.mocked(cxcLubrikcaService.proponerCierre).mockResolvedValue({ solicitud: null });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getAllByRole('button', { name: /proponer cierre/i })[0]);
    await waitFor(() => {
      expect(cxcLubrikcaService.proponerCierre).toHaveBeenCalledWith('b1');
    });
    expect(await screen.findByText(/cierre propuesto/i)).toBeInTheDocument();
  });

  it('confirma el cierre con aprobado=true y comentarios', async () => {
    vi.mocked(cxcLubrikcaService.confirmarCierre).mockResolvedValue(bandeja as never);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getAllByRole('button', { name: /^confirmar$/i })[0]);
    const dialog = within(await screen.findByRole('dialog'));
    await user.type(dialog.getByLabelText(/comentarios/i), 'Revisado y ok');
    await user.click(dialog.getByRole('button', { name: /confirmar cierre/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.confirmarCierre).toHaveBeenCalledWith('b1', {
        aprobado: true,
        comentarios: 'Revisado y ok',
      });
    });
  });

  it('muestra un error de snackbar cuando proponer falla (rol denegado)', async () => {
    vi.mocked(cxcLubrikcaService.proponerCierre).mockRejectedValue(
      new Error(JSON.stringify({ detail: 'No tiene permiso para cerrar.' })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('SO-0001');
    await user.click(screen.getAllByRole('button', { name: /proponer cierre/i })[0]);
    expect(await screen.findByText(/no tiene permiso para cerrar/i)).toBeInTheDocument();
  });
});
