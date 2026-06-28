import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/notificacionesService', () => ({
  notificacionesService: {
    misNotificaciones: vi.fn(),
    marcarLeida: vi.fn(),
  },
}));

import { notificacionesService } from '../services/notificacionesService';
import NotificacionesPage from '../pages/Notificaciones/NotificacionesPage';

const noLeida = {
  id_notificacion: 'n1',
  tipo: 'INFO',
  titulo: 'Pedido aprobado',
  mensaje: 'Tu pedido fue aprobado',
  leida: false,
  fecha_lectura: null,
  url_accion: '',
  metadata: null,
  fecha_creacion: '2026-06-24T10:00:00Z',
};

const leida = {
  ...noLeida,
  id_notificacion: 'n2',
  titulo: 'Bienvenida',
  mensaje: 'Bienvenido al sistema',
  leida: true,
  fecha_lectura: '2026-06-24T09:00:00Z',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotificacionesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NotificacionesPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza el encabezado y la lista de notificaciones', async () => {
    vi.mocked(notificacionesService.misNotificaciones).mockResolvedValue([noLeida, leida]);
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Notificaciones' })).toBeInTheDocument();
    expect(await screen.findByText('Pedido aprobado')).toBeInTheDocument();
    expect(screen.getByText('Bienvenida')).toBeInTheDocument();
  });

  it('muestra el estado vacío cuando no hay notificaciones', async () => {
    vi.mocked(notificacionesService.misNotificaciones).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('Sin notificaciones')).toBeInTheDocument();
  });

  it('al activar "Solo no leídas" reconsulta con el filtro', async () => {
    vi.mocked(notificacionesService.misNotificaciones).mockResolvedValue([noLeida, leida]);
    renderPage();
    await screen.findByText('Pedido aprobado');

    await userEvent.click(screen.getByLabelText('Solo no leídas'));

    await waitFor(() => {
      expect(notificacionesService.misNotificaciones).toHaveBeenCalledWith(true);
    });
  });

  it('marca una notificación como leída', async () => {
    vi.mocked(notificacionesService.misNotificaciones).mockResolvedValue([noLeida]);
    vi.mocked(notificacionesService.marcarLeida).mockResolvedValue({ ...noLeida, leida: true });
    renderPage();
    await screen.findByText('Pedido aprobado');

    await userEvent.click(screen.getByRole('button', { name: 'Marcar como leída' }));

    await waitFor(() => {
      expect(notificacionesService.marcarLeida).toHaveBeenCalledWith('n1');
    });
  });

  it('muestra una alerta de error si la carga falla', async () => {
    vi.mocked(notificacionesService.misNotificaciones).mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
  });
});
