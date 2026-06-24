import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  fetchBlob: vi.fn(),
  API_URL: 'http://localhost:8000/api',
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post } from '../services/api';
import DespachosPage from '../pages/Despacho/DespachosPage';

const despachoPendiente = {
  id_despacho: 'd1',
  id_empresa: 'e1',
  numero_despacho: 'DESP-001',
  id_nota_venta: 'nv1',
  numero_nota_venta: 'NV-001',
  fecha_despacho: '2026-06-24T10:00:00Z',
  id_almacen_origen: 'a1',
  direccion_destino: 'Av. Principal 123',
  estado_despacho: 'PENDIENTE',
};

const despachoEnRuta = {
  ...despachoPendiente,
  id_despacho: 'd2',
  numero_despacho: 'DESP-002',
  direccion_destino: 'Calle Sur 45',
  estado_despacho: 'EN_RUTA',
};

const despachoEntregado = {
  ...despachoPendiente,
  id_despacho: 'd3',
  numero_despacho: 'DESP-003',
  direccion_destino: 'Calle Norte 9',
  estado_despacho: 'ENTREGADO',
};

const notaElegible = {
  id_nota_venta: 'nv1',
  numero_nota_venta: 'NV-001',
  estado: 'ENTREGADA',
};
const notaBorrador = {
  id_nota_venta: 'nv2',
  numero_nota_venta: 'NV-002',
  estado: 'BORRADOR',
};
const almacen = { id_almacen: 'a1', nombre_almacen: 'Almacén Central', id_empresa: 'e1' };

let despachosResult: unknown[] = [despachoPendiente, despachoEnRuta, despachoEntregado];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/despacho/despachos')) return Promise.resolve(despachosResult);
    if (url.startsWith('/despacho/detalles-despacho'))
      return Promise.resolve([
        {
          id_detalle_despacho: 'l1',
          id_despacho: 'd1',
          id_producto: 'p1',
          nombre_producto: 'Producto A',
          cantidad_despachada: '5',
          id_unidad_medida: 'u1',
          unidad_medida: 'UND',
        },
      ]);
    if (url.startsWith('/ventas/notas-venta')) return Promise.resolve([notaElegible, notaBorrador]);
    if (url.startsWith('/almacenes/almacenes')) return Promise.resolve([almacen]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DespachosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DespachosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    despachosResult = [despachoPendiente, despachoEnRuta, despachoEntregado];
    setupGet();
  });

  it('lista los despachos con número, nota y estado', async () => {
    renderPage();
    expect(await screen.findByText('DESP-001')).toBeInTheDocument();
    expect(screen.getAllByText('NV-001').length).toBeGreaterThan(0);
    expect(screen.getByText('Pendiente')).toBeInTheDocument();
    expect(screen.getByText('En ruta')).toBeInTheDocument();
    expect(screen.getByText('Entregado')).toBeInTheDocument();
  });

  it('filtra por estado y arma el querystring', async () => {
    renderPage();
    await screen.findByText('DESP-001');
    fireEvent.mouseDown(screen.getByLabelText('Estado'));
    fireEvent.click(await screen.findByRole('option', { name: 'En ruta' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/despacho/despachos/?empresa=e1&estado=EN_RUTA'),
    );
  });

  it('gating de transiciones: PENDIENTE habilita Iniciar ruta y Cancelar; deshabilita Entregar/Devolver', async () => {
    renderPage();
    await screen.findByText('DESP-001');
    const fila = screen.getByText('DESP-001').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Iniciar ruta' })).toBeEnabled();
    expect(within(fila).getByRole('button', { name: 'Cancelar' })).toBeEnabled();
    expect(within(fila).getByRole('button', { name: 'Entregar' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Devolver' })).toBeDisabled();
  });

  it('gating de transiciones: EN_RUTA habilita Entregar y Devolver; deshabilita Iniciar ruta/Cancelar', async () => {
    renderPage();
    await screen.findByText('DESP-002');
    const fila = screen.getByText('DESP-002').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Entregar' })).toBeEnabled();
    expect(within(fila).getByRole('button', { name: 'Devolver' })).toBeEnabled();
    expect(within(fila).getByRole('button', { name: 'Iniciar ruta' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Cancelar' })).toBeDisabled();
  });

  it('gating de transiciones: ENTREGADO (terminal) deshabilita todas las acciones', async () => {
    renderPage();
    await screen.findByText('DESP-003');
    const fila = screen.getByText('DESP-003').closest('tr')!;
    for (const accion of ['Iniciar ruta', 'Entregar', 'Devolver', 'Cancelar']) {
      expect(within(fila).getByRole('button', { name: accion })).toBeDisabled();
    }
  });

  it('valida campos requeridos al crear desde nota de venta', async () => {
    renderPage();
    await screen.findByText('DESP-001');
    fireEvent.click(screen.getByRole('button', { name: 'Crear desde nota de venta' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Crear despacho' }));
    expect(
      await screen.findByText(/Seleccione la nota de venta, el almacén/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('solo ofrece notas de venta elegibles (ENTREGADA/FACTURADA)', async () => {
    renderPage();
    await screen.findByText('DESP-001');
    fireEvent.click(screen.getByRole('button', { name: 'Crear desde nota de venta' }));
    fireEvent.mouseDown(await screen.findByLabelText(/Nota de venta/));
    expect(await screen.findByRole('option', { name: /NV-001/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /NV-002/ })).not.toBeInTheDocument();
  });

  it('crea un despacho desde la nota de venta enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_despacho: 'd9' });
    renderPage();
    await screen.findByText('DESP-001');
    fireEvent.click(screen.getByRole('button', { name: 'Crear desde nota de venta' }));

    fireEvent.mouseDown(await screen.findByLabelText(/Nota de venta/));
    fireEvent.click(await screen.findByRole('option', { name: /NV-001/ }));
    fireEvent.mouseDown(screen.getByLabelText(/Almacén de origen/));
    fireEvent.click(await screen.findByRole('option', { name: 'Almacén Central' }));
    fireEvent.change(screen.getByLabelText(/Dirección de entrega/), {
      target: { value: 'Av. Test 1' },
    });
    fireEvent.change(screen.getByLabelText(/Observaciones/), { target: { value: 'urgente' } });

    fireEvent.click(screen.getByRole('button', { name: 'Crear despacho' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/despacho/despachos/desde-nota-venta/', {
        id_nota_venta: 'nv1',
        almacen_id: 'a1',
        direccion_entrega: 'Av. Test 1',
        observaciones: 'urgente',
      }),
    );
  });

  it('inicia la ruta de un PENDIENTE con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_despacho: 'd1', estado_despacho: 'EN_RUTA' });
    renderPage();
    await screen.findByText('DESP-001');
    const fila = screen.getByText('DESP-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Iniciar ruta' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/iniciar-ruta/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('no inicia la ruta si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('DESP-001');
    const fila = screen.getByText('DESP-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Iniciar ruta' }));
    expect(post).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('entrega un EN_RUTA pidiendo el receptor', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('María Receptora');
    vi.mocked(post).mockResolvedValue({ id_despacho: 'd2', estado_despacho: 'ENTREGADO' });
    renderPage();
    await screen.findByText('DESP-002');
    const fila = screen.getByText('DESP-002').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Entregar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/despacho/despachos/d2/entregar/', {
        receptor: 'María Receptora',
      }),
    );
    promptSpy.mockRestore();
  });

  it('no entrega si el receptor queda vacío', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('   ');
    renderPage();
    await screen.findByText('DESP-002');
    const fila = screen.getByText('DESP-002').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Entregar' }));
    expect(post).not.toHaveBeenCalled();
    promptSpy.mockRestore();
  });

  it('no entrega si se cancela el prompt (null)', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue(null);
    renderPage();
    await screen.findByText('DESP-002');
    const fila = screen.getByText('DESP-002').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Entregar' }));
    expect(post).not.toHaveBeenCalled();
    promptSpy.mockRestore();
  });

  it('devuelve un EN_RUTA con motivo', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('cliente ausente');
    vi.mocked(post).mockResolvedValue({ id_despacho: 'd2', estado_despacho: 'DEVUELTO' });
    renderPage();
    await screen.findByText('DESP-002');
    const fila = screen.getByText('DESP-002').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Devolver' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/despacho/despachos/d2/devolver/', {
        motivo: 'cliente ausente',
      }),
    );
    promptSpy.mockRestore();
  });

  it('cancela un PENDIENTE con motivo', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('pedido duplicado');
    vi.mocked(post).mockResolvedValue({ id_despacho: 'd1', estado_despacho: 'CANCELADO' });
    renderPage();
    await screen.findByText('DESP-001');
    const fila = screen.getByText('DESP-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Cancelar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/despacho/despachos/d1/cancelar/', {
        motivo: 'pedido duplicado',
      }),
    );
    promptSpy.mockRestore();
  });

  it('abre el drawer de detalle con las líneas y el enlace al PDF', async () => {
    renderPage();
    await screen.findByText('DESP-001');
    const fila = screen.getByText('DESP-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText('Líneas del despacho')).toBeInTheDocument();
    expect(await screen.findByText(/Producto A · 5 UND/)).toBeInTheDocument();
    const enlace = screen.getByRole('link', { name: /Ver nota de entrega/ });
    expect(enlace).toHaveAttribute('href', 'http://localhost:8000/api/despacho/despachos/d1/pdf/');
  });

  it('muestra error al fallar una transición', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('motivo');
    vi.mocked(post).mockRejectedValue(
      new Error(JSON.stringify({ error: 'Transición no permitida.' })),
    );
    renderPage();
    await screen.findByText('DESP-001');
    const fila = screen.getByText('DESP-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Cancelar' }));
    expect(await screen.findByText(/Transición no permitida/)).toBeInTheDocument();
    promptSpy.mockRestore();
  });
});
