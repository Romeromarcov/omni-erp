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
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, patch, del } from '../services/api';
import TicketsPage from '../pages/ServicioCliente/TicketsPage';

const ticketAbierto = {
  id_ticket: 't1',
  id_empresa: 'e1',
  numero_ticket: 'T-001',
  asunto: 'No enciende el equipo',
  descripcion: 'El equipo no enciende al pulsar el botón',
  id_categoria_ticket: 'cat-1',
  prioridad: 'ALTA',
  estado_ticket: 'ABIERTO',
};

const ticketCerrado = {
  ...ticketAbierto,
  id_ticket: 't2',
  numero_ticket: 'T-002',
  asunto: 'Consulta resuelta',
  estado_ticket: 'CERRADO',
  prioridad: 'BAJA',
};

const categoriaApi = {
  id_categoria_ticket: 'cat-1',
  id_empresa: 'e1',
  nombre_categoria: 'Hardware',
  activo: true,
};

const interaccionApi = {
  id_interaccion: 'i1',
  id_ticket: 't1',
  tipo_interaccion: 'COMENTARIO',
  contenido: 'Comentario inicial',
  fecha_hora_interaccion: '2026-06-24T10:00:00Z',
};

let ticketsResult: unknown[] = [ticketAbierto, ticketCerrado];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/servicio-cliente/categorias-ticket/activas'))
      return Promise.resolve([categoriaApi]);
    if (url.startsWith('/servicio-cliente/interacciones-ticket'))
      return Promise.resolve([interaccionApi]);
    if (url.startsWith('/servicio-cliente/tickets-soporte')) return Promise.resolve(ticketsResult);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TicketsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TicketsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ticketsResult = [ticketAbierto, ticketCerrado];
    setupGet();
  });

  it('lista los tickets con categoría, prioridad y estado', async () => {
    renderPage();
    expect(await screen.findByText('No enciende el equipo')).toBeInTheDocument();
    expect(screen.getByText('T-001')).toBeInTheDocument();
    expect(screen.getAllByText('Hardware').length).toBeGreaterThan(0);
    expect(screen.getByText('Alta')).toBeInTheDocument();
    expect(screen.getByText('Abierto')).toBeInTheDocument();
  });

  it('filtra por estado y arma el querystring', async () => {
    renderPage();
    await screen.findByText('No enciende el equipo');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'Cerrado' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/servicio-cliente/tickets-soporte/?id_empresa=e1&estado_ticket=CERRADO',
      ),
    );
  });

  it('filtra por prioridad y arma el querystring', async () => {
    renderPage();
    await screen.findByText('No enciende el equipo');
    fireEvent.mouseDown(screen.getByLabelText('Prioridad'));
    fireEvent.click(await screen.findByRole('option', { name: 'Urgente' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/servicio-cliente/tickets-soporte/?id_empresa=e1&prioridad=URGENTE',
      ),
    );
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('No enciende el equipo');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo ticket' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(
      await screen.findByText(/Complete número, categoría, asunto y descripción/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un ticket enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_ticket: 't3' });
    renderPage();
    await screen.findByText('No enciende el equipo');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo ticket' }));
    fireEvent.change(await screen.findByLabelText(/Número de ticket/), {
      target: { value: 'T-009' },
    });
    fireEvent.mouseDown(await screen.findByLabelText(/Categoría/));
    fireEvent.click(await screen.findByRole('option', { name: 'Hardware' }));
    fireEvent.change(screen.getByLabelText(/Asunto/), { target: { value: 'Pantalla rota' } });
    fireEvent.change(screen.getByLabelText(/Descripción/), {
      target: { value: 'La pantalla está rota' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/servicio-cliente/tickets-soporte/',
        expect.objectContaining({
          id_empresa: 'e1',
          numero_ticket: 'T-009',
          asunto: 'Pantalla rota',
          id_categoria_ticket: 'cat-1',
          prioridad: 'MEDIA',
          estado_ticket: 'ABIERTO',
        }),
      ),
    );
  });

  it('edita un ticket enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_ticket: 't1' });
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const asunto = await screen.findByLabelText(/Asunto/);
    fireEvent.change(asunto, { target: { value: 'Asunto editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/servicio-cliente/tickets-soporte/t1/',
        expect.objectContaining({ asunto: 'Asunto editado' }),
      ),
    );
  });

  it('elimina un ticket con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('abre el detalle y muestra el timeline de interacciones', async () => {
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText('Ticket T-001')).toBeInTheDocument();
    expect(await screen.findByText('Comentario inicial')).toBeInTheDocument();
    expect(screen.getByText('Historial de interacciones')).toBeInTheDocument();
  });

  it('agrega un comentario desde el detalle', async () => {
    vi.mocked(post).mockResolvedValue({ id_interaccion: 'i2' });
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.change(await screen.findByLabelText(/Agregar comentario/), {
      target: { value: 'Nuevo comentario' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar comentario' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/servicio-cliente/interacciones-ticket/agregar_comentario/',
        { ticket_id: 't1', contenido: 'Nuevo comentario' },
      ),
    );
  });

  it('valida comentario vacío en el detalle', async () => {
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Agregar comentario' }));
    expect(await screen.findByText(/Escriba un comentario/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('asigna un agente desde el detalle', async () => {
    vi.mocked(post).mockResolvedValue({ id_ticket: 't1', estado_ticket: 'ASIGNADO' });
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.change(await screen.findByLabelText(/ID del agente/), {
      target: { value: 'ag-7' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar agente' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/asignar_agente/', {
        agente_id: 'ag-7',
      }),
    );
  });

  it('valida agente vacío al asignar', async () => {
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Asignar agente' }));
    expect(await screen.findByText(/Indique el ID del agente/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('cambia el estado desde el detalle con comentario', async () => {
    vi.mocked(post).mockResolvedValue({ id_ticket: 't1', estado_ticket: 'EN_PROGRESO' });
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Nuevo estado/));
    fireEvent.click(await screen.findByRole('option', { name: 'En progreso' }));
    fireEvent.change(screen.getByLabelText(/^Comentario/), { target: { value: 'En análisis' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cambiar estado' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/cambiar_estado/', {
        estado: 'EN_PROGRESO',
        comentario: 'En análisis',
      }),
    );
  });

  it('escala el ticket desde el detalle', async () => {
    vi.mocked(post).mockResolvedValue({ id_ticket: 't1', estado_ticket: 'ESCALADO' });
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.change(await screen.findByLabelText(/Razón de escalamiento/), {
      target: { value: 'sin solución' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Escalar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/escalar/', {
        razon: 'sin solución',
      }),
    );
  });

  it('en un ticket cerrado el detalle bloquea las acciones', async () => {
    renderPage();
    await screen.findByText('Consulta resuelta');
    const fila = screen.getByText('Consulta resuelta').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText(/no admite más acciones/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Asignar agente' })).not.toBeInTheDocument();
  });

  it('muestra error al fallar el cambio de estado', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'Estado inválido.' })));
    renderPage();
    await screen.findByText('No enciende el equipo');
    const fila = screen.getByText('No enciende el equipo').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cambiar estado' }));
    expect(await screen.findByText(/Estado inválido/)).toBeInTheDocument();
  });

  it('muestra error al fallar la creación', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ numero_ticket: ['duplicado'] })));
    renderPage();
    await screen.findByText('No enciende el equipo');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo ticket' }));
    fireEvent.change(await screen.findByLabelText(/Número de ticket/), {
      target: { value: 'T-001' },
    });
    fireEvent.mouseDown(await screen.findByLabelText(/Categoría/));
    fireEvent.click(await screen.findByRole('option', { name: 'Hardware' }));
    fireEvent.change(screen.getByLabelText(/Asunto/), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText(/Descripción/), { target: { value: 'y' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/duplicado/)).toBeInTheDocument();
  });
});
