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

import { get, post, del } from '../services/api';
import IngestasBotsPage from '../pages/Bots/IngestasBotsPage';
import { resumenIngesta } from '../pages/Bots/utils';

const base = {
  odoo_ref: '',
  fecha_creacion: '2026-12-01T10:00:00Z',
  fecha_actualizacion: '2026-12-01T10:00:00Z',
  resultado: {},
};

const pagoIncompleto = {
  ...base,
  id_ingesta: 'i1',
  kind: 'pago',
  estado: 'INCOMPLETO',
  incompleto: ['referencia'],
  auto: true,
  idempotency_key: 'k1',
  payload: { cliente: 'Taller Rojas', monto: '50', moneda: 'USD' },
};

const pedido = {
  ...base,
  id_ingesta: 'i2',
  kind: 'pedido',
  estado: 'PROCESADO',
  incompleto: [],
  auto: false,
  idempotency_key: 'k2',
  resultado: { numero: 'PED-00001' },
  payload: { cliente: 'Bodega Sur', rif: 'J-123456789' },
};

const usuarios = [
  { id: 'u1', username: 'ana', email: 'a@x.com', first_name: 'Ana', last_name: 'Pérez', is_active: true, es_superusuario_omni: false },
];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/bots/ingest/')) {
      const soloIncompletas = url.includes('estado=INCOMPLETO');
      return Promise.resolve(soloIncompletas ? [pagoIncompleto] : [pagoIncompleto, pedido]);
    }
    if (url.startsWith('/bots/usuarios/'))
      return Promise.resolve([
        { id_bot_usuario: 'b1', id_empresa: 'e1', telegram_user_id: 111222333, usuario: 'u1', nombre: 'Ana TG', activo: true },
      ]);
    if (url.startsWith('/core/usuarios/')) return Promise.resolve(usuarios);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <IngestasBotsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IngestasBotsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista las ingestas con estado, tipo, resumen y lo que falta', async () => {
    renderPage();
    expect(await screen.findByText('Taller Rojas · 50 USD')).toBeInTheDocument();
    expect(screen.getByText('Bodega Sur')).toBeInTheDocument();
    expect(screen.getByText('referencia')).toBeInTheDocument();
    expect(screen.getByText('Automático')).toBeInTheDocument();
    expect(screen.getByText('Pago de cliente')).toBeInTheDocument();
  });

  it('«Ver incompletas» filtra por estado en el backend', async () => {
    renderPage();
    await screen.findByText('Bodega Sur');
    fireEvent.click(screen.getByRole('button', { name: 'Ver incompletas' }));
    await waitFor(() => expect(screen.queryByText('Bodega Sur')).not.toBeInTheDocument());
    const urls = vi.mocked(get).mock.calls.map((c) => c[0]);
    expect(urls).toContain('/bots/ingest/?estado=INCOMPLETO');
  });

  it('muestra el detalle del borrador y el resultado en Omni', async () => {
    renderPage();
    const fila = (await screen.findByText('Bodega Sur')).closest('tr') as HTMLElement;
    fireEvent.click(within(fila).getByRole('button', { name: 'Ver' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/"rif": "J-123456789"/)).toBeInTheDocument();
    expect(within(dialogo).getByText(/PED-00001/)).toBeInTheDocument();
  });

  it('solo los pagos incompletos o en borrador ofrecen «Completar»', async () => {
    renderPage();
    const filaPedido = (await screen.findByText('Bodega Sur')).closest('tr') as HTMLElement;
    expect(within(filaPedido).queryByRole('button', { name: 'Completar' })).not.toBeInTheDocument();
    const filaPago = screen.getByText('Taller Rojas · 50 USD').closest('tr') as HTMLElement;
    expect(within(filaPago).getByRole('button', { name: 'Completar' })).toBeInTheDocument();
  });

  it('completa un pago enviando solo los campos que cambiaron', async () => {
    vi.mocked(post).mockResolvedValue({ ...pagoIncompleto, estado: 'BORRADOR', incompleto: [] });
    renderPage();
    const fila = (await screen.findByText('Taller Rojas · 50 USD')).closest('tr') as HTMLElement;
    fireEvent.click(within(fila).getByRole('button', { name: 'Completar' }));
    const dialogo = await screen.findByRole('dialog');
    const guardar = within(dialogo).getByRole('button', { name: 'Guardar cambios' });
    expect(guardar).toBeDisabled(); // nada cambió todavía
    fireEvent.change(within(dialogo).getByLabelText('Referencia'), { target: { value: 'ABC123' } });
    expect(guardar).toBeEnabled();
    fireEvent.click(guardar);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/bots/ingest/i1/completar/', { cambios: { referencia: 'ABC123' } }),
    );
  });

  it('muestra el error del backend al completar', async () => {
    vi.mocked(post).mockRejectedValue(new Error('{"error":"Esta ingesta ya fue sincronizada; edítala en Odoo."}'));
    renderPage();
    const fila = (await screen.findByText('Taller Rojas · 50 USD')).closest('tr') as HTMLElement;
    fireEvent.click(within(fila).getByRole('button', { name: 'Completar' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText('Referencia'), { target: { value: 'X1' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar cambios' }));
    expect(await within(dialogo).findByText(/edítala en Odoo/)).toBeInTheDocument();
  });

  it('administra usuarios de Telegram: lista, autoriza y quita', async () => {
    vi.mocked(post).mockResolvedValue({});
    vi.mocked(del).mockResolvedValue(undefined as never);
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Usuarios de Telegram' }));
    expect(await screen.findByText('111222333')).toBeInTheDocument();
    expect(await screen.findByText('Ana Pérez (ana)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Autorizar usuario' }));
    const dialogo = await screen.findByRole('dialog');
    const guardar = within(dialogo).getByRole('button', { name: 'Guardar' });
    expect(guardar).toBeDisabled();
    fireEvent.change(within(dialogo).getByLabelText(/^ID numérico/), { target: { value: '555' } });
    fireEvent.mouseDown(within(dialogo).getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: 'Ana Pérez (ana)' }));
    fireEvent.click(guardar);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/bots/usuarios/', { telegram_user_id: 555, usuario: 'u1', nombre: '' }),
    );
  });

  it('quita la autorización de un usuario tras confirmar', async () => {
    vi.mocked(del).mockResolvedValue(undefined as never);
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Usuarios de Telegram' }));
    const fila = (await screen.findByText('111222333')).closest('tr') as HTMLElement;
    fireEvent.click(within(fila).getByRole('button', { name: 'Quitar' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Quitar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/bots/usuarios/b1/'));
  });
});

describe('resumenIngesta', () => {
  it('prioriza cliente, luego nombre, proveedor o rif, y agrega el monto', () => {
    expect(resumenIngesta({ payload: { nombre: 'Pedro' } })).toBe('Pedro');
    expect(resumenIngesta({ payload: { proveedor: 'Lubri SA', monto: '900', moneda: 'USD' } })).toBe('Lubri SA · 900 USD');
    expect(resumenIngesta({ payload: {} })).toBe('—');
  });
});
