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
import ConceptosNominaPage from '../pages/Nomina/ConceptosNominaPage';

const conceptoDevengado = {
  id_concepto_nomina: 'c1',
  id_empresa: 'e1',
  codigo_concepto: 'DEV-001',
  nombre_concepto: 'Bono productividad',
  tipo_concepto: 'DEVENGADO',
  categoria: 'BONO',
  formula_calculo: null,
  es_fijo: true,
  monto_fijo: '150.0000',
  es_porcentaje: false,
  porcentaje: null,
  activo: true,
};

const conceptoDeduccion = {
  ...conceptoDevengado,
  id_concepto_nomina: 'c2',
  codigo_concepto: 'DED-001',
  nombre_concepto: 'Retención IVSS',
  tipo_concepto: 'DEDUCCION',
  categoria: 'SEGURO_SOCIAL',
  es_fijo: false,
  monto_fijo: null,
  es_porcentaje: true,
  porcentaje: '4.00',
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/nomina/conceptos-nomina/por_tipo')) {
      return Promise.resolve([conceptoDeduccion]);
    }
    if (url.startsWith('/nomina/conceptos-nomina')) {
      return Promise.resolve([conceptoDevengado, conceptoDeduccion]);
    }
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ConceptosNominaPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConceptosNominaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista los conceptos con tipo y categoría', async () => {
    renderPage();
    expect(await screen.findByText('Bono productividad')).toBeInTheDocument();
    expect(screen.getByText('Retención IVSS')).toBeInTheDocument();
    expect(screen.getByText('Seguro social')).toBeInTheDocument();
  });

  it('filtra por tipo usando la acción por_tipo', async () => {
    renderPage();
    await screen.findByText('Bono productividad');
    fireEvent.mouseDown(screen.getByLabelText('Tipo'));
    fireEvent.click(await screen.findByRole('option', { name: 'Deducción' }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/nomina/conceptos-nomina/por_tipo/?tipo=DEDUCCION'),
    );
  });

  it('valida campos requeridos al crear', async () => {
    renderPage();
    await screen.findByText('Bono productividad');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo concepto' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete el código y el nombre/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un concepto fijo enviando el payload', async () => {
    vi.mocked(post).mockResolvedValue({ id_concepto_nomina: 'c3' });
    renderPage();
    await screen.findByText('Bono productividad');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo concepto' }));
    fireEvent.change(await screen.findByLabelText(/Código/), { target: { value: 'DEV-009' } });
    fireEvent.change(screen.getByLabelText(/Nombre/), { target: { value: 'Comisión' } });
    fireEvent.click(screen.getByLabelText('Monto fijo'));
    fireEvent.change(await screen.findByLabelText(/Valor del monto fijo/), {
      target: { value: '99' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/nomina/conceptos-nomina/',
        expect.objectContaining({
          id_empresa: 'e1',
          codigo_concepto: 'DEV-009',
          nombre_concepto: 'Comisión',
          tipo_concepto: 'DEVENGADO',
          es_fijo: true,
          monto_fijo: '99',
          es_porcentaje: false,
          porcentaje: null,
        }),
      ),
    );
  });

  it('edita un concepto enviando el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_concepto_nomina: 'c1' });
    renderPage();
    await screen.findByText('Bono productividad');
    const fila = screen.getByText('Bono productividad').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar' }));
    const nombre = await screen.findByLabelText(/Nombre/);
    fireEvent.change(nombre, { target: { value: 'Bono editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/nomina/conceptos-nomina/c1/',
        expect.objectContaining({ nombre_concepto: 'Bono editado' }),
      ),
    );
  });

  it('elimina un concepto con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Bono productividad');
    const fila = screen.getByText('Bono productividad').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/nomina/conceptos-nomina/c1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si se cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await screen.findByText('Bono productividad');
    const fila = screen.getByText('Bono productividad').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('muestra error al fallar el guardado', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ codigo_concepto: ['Ya existe.'] })));
    renderPage();
    await screen.findByText('Bono productividad');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo concepto' }));
    fireEvent.change(await screen.findByLabelText(/Código/), { target: { value: 'DEV-001' } });
    fireEvent.change(screen.getByLabelText(/Nombre/), { target: { value: 'Duplicado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Ya existe/)).toBeInTheDocument();
  });
});
