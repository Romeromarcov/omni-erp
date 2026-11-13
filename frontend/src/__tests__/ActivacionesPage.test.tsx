import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import ActivacionesPage from '../pages/Activaciones/ActivacionesPage';
import { localAISO, mensajeActivacion, textoUsos } from '../pages/Activaciones/utils';

const calendario = {
  id_calendario: 'c1',
  id_empresa: 'e1',
  nombre: 'Activaciones',
  google_calendar_id: 'abc@group.calendar.google.com',
  zona_horaria: 'America/Caracas',
  es_predeterminado: true,
  activo: true,
};

const recursos = [
  { id_recurso: 'r1', id_empresa: 'e1', calendario: 'c1', codigo: 'promotoras', nombre: 'Promotoras', capacidad: 2, activo: true },
  { id_recurso: 'r2', id_empresa: 'e1', calendario: 'c1', codigo: 'igloos', nombre: 'Igloos', capacidad: 3, activo: true },
];

const evento = {
  id_evento: 'ev1',
  id_empresa: 'e1',
  calendario: 'c1',
  cliente: null,
  cliente_nombre: 'Bodega La Esquina',
  vendedor: 'u1',
  vendedor_nombre: 'Ana Pérez',
  ubicacion: 'Av. Principal',
  inicio: '2026-12-05T13:00:00Z',
  fin: '2026-12-05T17:00:00Z',
  materiales: ['toldo'],
  notas: '',
  estado: 'PROGRAMADO',
  origen: 'BOT',
  google_event_id: '',
  sync_error: 'No se pudo sincronizar con Google Calendar.',
  usos: [
    { recurso: 'r1', recurso_codigo: 'promotoras', cantidad: 1 },
    { recurso: 'r2', recurso_codigo: 'igloos', cantidad: 2 },
  ],
};

function setupGet(eventos: unknown[] = [evento]) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/activaciones/eventos/')) return Promise.resolve(eventos);
    if (url.startsWith('/activaciones/calendarios/c1/disponibilidad/'))
      return Promise.resolve([
        { codigo: 'promotoras', nombre: 'Promotoras', capacidad: 2, usado: 1, libres: 1 },
        { codigo: 'igloos', nombre: 'Igloos', capacidad: 3, usado: 3, libres: 0 },
      ]);
    if (url.startsWith('/activaciones/calendarios/')) return Promise.resolve([calendario]);
    if (url.startsWith('/activaciones/recursos/')) return Promise.resolve(recursos);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ActivacionesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ActivacionesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista los eventos con recursos, origen y aviso de sync con Google', async () => {
    renderPage();
    expect(await screen.findByText('Bodega La Esquina')).toBeInTheDocument();
    expect(screen.getByText('Ana Pérez')).toBeInTheDocument();
    expect(screen.getByText('promotoras ×1 · igloos ×2')).toBeInTheDocument();
    expect(screen.getByText('Bot')).toBeInTheDocument();
    expect(screen.getByText('Sin sincronizar con Google')).toBeInTheDocument();
  });

  it('cancela un evento programado tras confirmar', async () => {
    vi.mocked(post).mockResolvedValue({ ...evento, estado: 'CANCELADO' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/Se liberan los recursos/)).toBeInTheDocument();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar evento' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/activaciones/eventos/ev1/cancelar/', {}));
  });

  it('crea un evento enviando los recursos por código', async () => {
    vi.mocked(post).mockResolvedValue(evento);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Nuevo evento' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText(/^Cliente/), { target: { value: 'Kiosco 24' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Ubicación/), { target: { value: 'Plaza Mayor' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Inicio/), { target: { value: '2026-12-06T09:00' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Fin/), { target: { value: '2026-12-06T13:00' } });
    fireEvent.change(await within(dialogo).findByLabelText(/Promotoras/), { target: { value: '2' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Materiales/), { target: { value: 'toldo, igloo grande' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear evento' }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    const [url, body] = vi.mocked(post).mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe('/activaciones/eventos/');
    expect(body.cliente_nombre).toBe('Kiosco 24');
    expect(body.calendario).toBe('c1');
    expect(body.usos).toEqual({ promotoras: 2, igloos: 0 });
    expect(body.materiales).toEqual(['toldo', 'igloo grande']);
    expect(body.inicio).toBe(localAISO('2026-12-06T09:00'));
  });

  it('muestra el mensaje del 409 de capacidad sin imprimir el detalle crudo', async () => {
    vi.mocked(post).mockRejectedValue(
      new Error(
        JSON.stringify({
          error: 'No hay promotoras suficientes en ese horario: quedan 0 de 2 y pides 1.',
          detalle: { recurso: 'promotoras', libres: 0 },
        }),
      ),
    );
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Nuevo evento' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText(/^Cliente/), { target: { value: 'Kiosco 24' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Ubicación/), { target: { value: 'Plaza Mayor' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Inicio/), { target: { value: '2026-12-06T09:00' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Fin/), { target: { value: '2026-12-06T13:00' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear evento' }));

    const alerta = await within(dialogo).findByRole('alert');
    expect(alerta).toHaveTextContent('No hay promotoras suficientes en ese horario: quedan 0 de 2 y pides 1.');
    expect(alerta).not.toHaveTextContent('object Object');
  });

  it('no permite crear si el fin no es posterior al inicio', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Nuevo evento' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText(/^Cliente/), { target: { value: 'K' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Ubicación/), { target: { value: 'P' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Inicio/), { target: { value: '2026-12-06T13:00' } });
    fireEvent.change(within(dialogo).getByLabelText(/^Fin/), { target: { value: '2026-12-06T09:00' } });
    expect(within(dialogo).getByRole('button', { name: 'Crear evento' })).toBeDisabled();
  });

  it('consulta la disponibilidad por horario y muestra los libres', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Disponibilidad' }));
    expect(screen.getByText(/Indica un horario/)).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText(/^Inicio/), { target: { value: '2026-12-06T09:00' } });
    fireEvent.change(screen.getByLabelText(/^Fin/), { target: { value: '2026-12-06T13:00' } });
    expect(await screen.findByText(/libres de 2/)).toBeInTheDocument();
    expect(screen.getByText(/libres de 3/)).toBeInTheDocument();
    const urls = vi.mocked(get).mock.calls.map((c) => c[0]);
    expect(urls.some((u) => u.startsWith('/activaciones/calendarios/c1/disponibilidad/?inicio='))).toBe(true);
  });

  it('edita la capacidad de un recurso', async () => {
    vi.mocked(patch).mockResolvedValue({ ...recursos[0], capacidad: 5 });
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Calendarios y recursos' }));
    const fila = (await screen.findByText('promotoras')).closest('tr') as HTMLElement;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText(/^Capacidad/), { target: { value: '5' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/activaciones/recursos/r1/', { nombre: 'Promotoras', capacidad: 5 }),
    );
  });

  it('elimina un recurso (borrado lógico) tras confirmar', async () => {
    vi.mocked(del).mockResolvedValue(undefined as never);
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Calendarios y recursos' }));
    const fila = (await screen.findByText('igloos')).closest('tr') as HTMLElement;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/borrado lógico/)).toBeInTheDocument();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/activaciones/recursos/r2/'));
  });

  it('crea un calendario predeterminado con su zona horaria', async () => {
    vi.mocked(post).mockResolvedValue(calendario);
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Calendarios y recursos' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Nuevo calendario' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText(/^Nombre/), { target: { value: 'Ferias' } });
    fireEvent.click(within(dialogo).getByLabelText(/predeterminado/));
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/activaciones/calendarios/', {
        nombre: 'Ferias',
        google_calendar_id: '',
        zona_horaria: 'America/Caracas',
        es_predeterminado: true,
      }),
    );
  });
});

describe('utils de activaciones', () => {
  it('localAISO devuelve vacío ante valores inválidos', () => {
    expect(localAISO('')).toBe('');
    expect(localAISO('no-es-fecha')).toBe('');
    expect(localAISO('2026-12-06T09:00')).toMatch(/^2026-12-06T\d{2}:00:00\.000Z$/);
  });

  it('textoUsos omite recursos en cero', () => {
    expect(textoUsos({ usos: [{ recurso: 'r', recurso_codigo: 'igloos', cantidad: 0 }] })).toBe('—');
  });

  it('mensajeActivacion extrae `error` del JSON y cae al mensaje genérico', () => {
    expect(mensajeActivacion(new Error('{"error":"Sin cupo"}'), 'x')).toBe('Sin cupo');
    expect(mensajeActivacion(new Error('{"nombre":["Ya existe"]}'), 'x')).toBe('nombre: Ya existe');
    expect(mensajeActivacion(null, 'fallback')).toBe('fallback');
  });
});
