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

import { get, post, del } from '../services/api';
import FeedbackPage from '../pages/ServicioCliente/FeedbackPage';

const feedbackApi = {
  id_feedback: 'f1',
  id_empresa: 'e1',
  tipo_feedback: 'QUEJA',
  calificacion: 2,
  comentarios: 'Demora en la atención',
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/servicio-cliente/feedback-cliente')) return Promise.resolve([feedbackApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <FeedbackPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('FeedbackPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista el feedback con tipo y calificación', async () => {
    renderPage();
    expect(await screen.findByText('Demora en la atención')).toBeInTheDocument();
    expect(screen.getByText('Queja')).toBeInTheDocument();
    expect(screen.getByText('2/5')).toBeInTheDocument();
  });

  it('filtra por tipo y arma el querystring', async () => {
    renderPage();
    await screen.findByText('Demora en la atención');
    fireEvent.mouseDown(screen.getByLabelText('Tipo'));
    fireEvent.click(await screen.findByRole('option', { name: 'Sugerencia' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        '/servicio-cliente/feedback-cliente/?id_empresa=e1&tipo_feedback=SUGERENCIA',
      ),
    );
  });

  it('crea feedback enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_feedback: 'f2' });
    renderPage();
    await screen.findByText('Demora en la atención');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo feedback' }));
    fireEvent.change(await screen.findByLabelText(/Calificación/), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/Comentarios/), { target: { value: 'Muy bien' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/servicio-cliente/feedback-cliente/',
        expect.objectContaining({
          id_empresa: 'e1',
          tipo_feedback: 'ENCUESTA_SATISFACCION',
          calificacion: 5,
          comentarios: 'Muy bien',
        }),
      ),
    );
  });

  it('crea feedback sin calificación (queda en null)', async () => {
    vi.mocked(post).mockResolvedValue({ id_feedback: 'f3' });
    renderPage();
    await screen.findByText('Demora en la atención');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo feedback' }));
    fireEvent.change(await screen.findByLabelText(/Comentarios/), { target: { value: 'Sugerencia' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/servicio-cliente/feedback-cliente/',
        expect.objectContaining({ calificacion: null, comentarios: 'Sugerencia' }),
      ),
    );
  });

  it('valida calificación fuera de rango', async () => {
    renderPage();
    await screen.findByText('Demora en la atención');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo feedback' }));
    fireEvent.change(await screen.findByLabelText(/Calificación/), { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/entero del 1 al 5/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('elimina feedback con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Demora en la atención');
    const fila = screen.getByText('Demora en la atención').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/servicio-cliente/feedback-cliente/f1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Demora en la atención');
    const fila = screen.getByText('Demora en la atención').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'tipo inválido' })));
    renderPage();
    await screen.findByText('Demora en la atención');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo feedback' }));
    fireEvent.change(await screen.findByLabelText(/Comentarios/), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/tipo inválido/)).toBeInTheDocument();
  });
});
