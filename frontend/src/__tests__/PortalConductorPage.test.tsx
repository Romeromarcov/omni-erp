import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  API_URL: 'http://localhost:8000/api',
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post } from '../services/api';
import PortalConductorPage from '../pages/Despacho/PortalConductorPage';

function renderConductor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PortalConductorPage />
    </QueryClientProvider>,
  );
}

describe('PortalConductorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockResolvedValue({
      empresa_id: 'e1',
      rutas: [
        {
          id_ruta: 'r1',
          codigo: 'RUTA-001',
          estado: 'EN_CURSO',
          fecha_ruta: '2026-11-24',
          vehiculo_placa: 'ABC-123',
          paradas: [
            {
              id_parada: 'par-1',
              secuencia: 1,
              estado: 'PENDIENTE',
              despacho_numero: 'DSP-500',
              direccion_texto: 'Las Mercedes, Caracas',
              latitud: '10.481000',
              longitud: '-66.858000',
              eta_estimada: '2026-11-24T15:00:00Z',
              waze_url: 'https://waze.com/ul?ll=10.481000,-66.858000&navigate=yes',
              google_maps_url: 'https://www.google.com/maps/dir/?api=1&destination=10.481000,-66.858000',
            },
          ],
        },
      ],
    });
  });

  it('lista rutas con Waze/Maps, verifica escaneo de bulto y registra ePOD con cobro en sitio', async () => {
    vi.mocked(post).mockImplementation((url: string) => {
      if (url.includes('/escanear-bulto/')) {
        return Promise.resolve({ id_parada: 'par-1', codigo_bulto: 'OIL-20W50', verificado: true });
      }
      return Promise.resolve({ parada: { id_parada: 'par-1' }, despacho_estado: 'ENTREGADO', pago_id: 'pag-1', ruta_completada: true });
    });

    renderConductor();
    expect(await screen.findByText(/RUTA-001 · Vehículo ABC-123/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Waze' })).toHaveAttribute(
      'href',
      'https://waze.com/ul?ll=10.481000,-66.858000&navigate=yes',
    );
    expect(screen.getByRole('link', { name: 'Google Maps' })).toHaveAttribute(
      'href',
      'https://www.google.com/maps/dir/?api=1&destination=10.481000,-66.858000',
    );

    // Escanear bulto
    fireEvent.click(screen.getByRole('button', { name: 'Escanear bulto' }));
    fireEvent.change(screen.getByLabelText('SKU o Código de Barras'), { target: { value: 'OIL-20W50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verificar bulto' }));
    await waitFor(() => expect(screen.getByText(/Bulto OIL-20W50 verificado/)).toBeInTheDocument());
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // ePOD con cobro en sitio
    const epodBtn = await screen.findByRole('button', { name: 'Registrar ePOD' });
    fireEvent.click(epodBtn);
    fireEvent.change(screen.getByLabelText('Receptor nombre'), { target: { value: 'Carlos Ruiz' } });
    fireEvent.click(screen.getByLabelText('Registrar cobro contra entrega'));
    fireEvent.change(screen.getByLabelText('Monto cobro'), { target: { value: '100.00' } });
    fireEvent.change(screen.getByLabelText('UUID Moneda'), { target: { value: 'm-usd' } });
    fireEvent.change(screen.getByLabelText('UUID Método Pago'), { target: { value: 'mp-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar ePOD' }));
    await waitFor(() => expect(screen.getByText(/ePOD registrado · Despacho ENTREGADO · Cobro aplicado/)).toBeInTheDocument());
  });
});
