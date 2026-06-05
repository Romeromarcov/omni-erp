/**
 * TEST-6 — Test de componente real con fetch real vía MSW.
 *
 * `NotificationBell` (components/NotificationBell.tsx) hace `fetcher(...)` real
 * contra `/notificaciones/.../mis-notificaciones/`. No se mockea `services/api`:
 * la petición HTTP la intercepta MSW. Se valida el render dependiente de datos
 * (badge con el conteo) y el estado vacío.
 */
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NotificationBell from '../components/NotificationBell';
import { server } from '../test/server';
import { apiUrl } from '../test/handlers';

function renderBell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NotificationBell (MSW)', () => {
  it('muestra el conteo de notificaciones no leídas que devuelve el backend', async () => {
    server.use(
      http.get(apiUrl('/notificaciones/notificaciones/mis-notificaciones/'), () =>
        HttpResponse.json([
          {
            id_notificacion: 'n-1',
            tipo: 'info',
            titulo: 'Pago recibido',
            mensaje: 'Se registró un pago',
            leida: false,
            fecha_lectura: null,
            url_accion: '',
            fecha_creacion: '2026-06-05T10:00:00Z',
          },
          {
            id_notificacion: 'n-2',
            tipo: 'info',
            titulo: 'Stock bajo',
            mensaje: 'Producto X bajo mínimo',
            leida: false,
            fecha_lectura: null,
            url_accion: '',
            fecha_creacion: '2026-06-05T11:00:00Z',
          },
        ]),
      ),
    );

    renderBell();

    // El badge refleja el conteo cargado desde la red.
    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument());

    // Al abrir el popover se listan los títulos provenientes del fetch real.
    await userEvent.click(screen.getByRole('button', { name: /notificaciones/i }));
    expect(await screen.findByText('Pago recibido')).toBeInTheDocument();
    expect(screen.getByText('Stock bajo')).toBeInTheDocument();
  });

  it('renderiza el estado vacío cuando el backend no devuelve notificaciones', async () => {
    // Usa el handler por defecto ([]).
    renderBell();

    await userEvent.click(screen.getByRole('button', { name: /notificaciones/i }));
    expect(await screen.findByText(/sin notificaciones pendientes/i)).toBeInTheDocument();
  });
});
