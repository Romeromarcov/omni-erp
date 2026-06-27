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
import NominaExtrasalarialPage from '../pages/Nomina/NominaExtrasalarialPage';

const procesoEnProceso = {
  id_proceso_extrasalarial: 'p1',
  id_empresa: 'e1',
  numero_proceso: 'EXTRA-001',
  tipo_proceso: 'AGUINALDO',
  fecha_proceso: '2026-06-27T00:00:00Z',
  fecha_corte: '2026-06-27',
  total_empleados: 0,
  total_monto: '0.0000',
  estado: 'EN_PROCESO',
  observaciones: null,
};

const procesoCompletado = {
  ...procesoEnProceso,
  id_proceso_extrasalarial: 'p2',
  numero_proceso: 'EXTRA-002',
  estado: 'COMPLETADO',
};

const reciboCalculado = {
  id_nomina_extrasalarial: 'r1',
  id_proceso_extrasalarial: 'p1',
  id_empleado: 7,
  periodo_inicio: '2026-01-01',
  periodo_fin: '2026-06-30',
  salario_promedio: '500.0000',
  dias_laborados: 180,
  monto_calculado: '250.0000',
  deducciones: '0.0000',
  monto_neto: '250.0000',
  estado: 'CALCULADA',
  fecha_calculo: '2026-06-27T00:00:00Z',
  observaciones: null,
};

const empleadoApi = {
  id: 7,
  empresa: 'e1',
  nombre: 'Ana',
  apellido: 'Pérez',
  cedula: 'V-1',
  cargo: null,
  fecha_ingreso: '2024-01-01',
  activo: true,
  documento_json: null,
  referencia_externa: null,
  contacto: null,
};

let procesosResult: unknown[] = [procesoEnProceso, procesoCompletado];

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/nomina/nominas-extrasalarial')) return Promise.resolve([reciboCalculado]);
    if (url.startsWith('/nomina/procesos-nomina-extrasalarial')) return Promise.resolve(procesosResult);
    if (url.startsWith('/rrhh/empleados')) return Promise.resolve([empleadoApi]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NominaExtrasalarialPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NominaExtrasalarialPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    procesosResult = [procesoEnProceso, procesoCompletado];
    setupGet();
  });

  it('lista los procesos con tipo y estado', async () => {
    renderPage();
    expect(await screen.findByText('EXTRA-001')).toBeInTheDocument();
    expect(screen.getByText('EXTRA-002')).toBeInTheDocument();
    expect(screen.getAllByText('Aguinaldo / Utilidades').length).toBeGreaterThan(0);
  });

  it('valida el número requerido al crear', async () => {
    renderPage();
    await screen.findByText('EXTRA-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proceso' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Indique el número del proceso/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un proceso enviando el payload con fecha ISO', async () => {
    vi.mocked(post).mockResolvedValue({ id_proceso_extrasalarial: 'p3' });
    renderPage();
    await screen.findByText('EXTRA-001');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proceso' }));
    fireEvent.change(await screen.findByLabelText(/Número de proceso/), {
      target: { value: 'EXTRA-009' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/nomina/procesos-nomina-extrasalarial/',
        expect.objectContaining({
          id_empresa: 'e1',
          numero_proceso: 'EXTRA-009',
          tipo_proceso: 'AGUINALDO',
          fecha_corte: expect.any(String),
        }),
      ),
    );
  });

  it('procesa un proceso EN_PROCESO con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_proceso_extrasalarial: 'p1', estado: 'COMPLETADO' });
    renderPage();
    await screen.findByText('EXTRA-001');
    const fila = screen.getByText('EXTRA-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Procesar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p1/procesar/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('aprueba un proceso COMPLETADO y bloquea Procesar', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockResolvedValue({ id_proceso_extrasalarial: 'p2', estado: 'APROBADO' });
    renderPage();
    await screen.findByText('EXTRA-002');
    const fila = screen.getByText('EXTRA-002').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Procesar' })).toBeDisabled();
    fireEvent.click(within(fila).getByRole('button', { name: 'Aprobar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p2/aprobar/', {}),
    );
    confirmSpy.mockRestore();
  });

  it('deshabilita Procesar/Editar/Eliminar en un proceso no EN_PROCESO', async () => {
    renderPage();
    await screen.findByText('EXTRA-002');
    const fila = screen.getByText('EXTRA-002').closest('tr')!;
    expect(within(fila).getByRole('button', { name: 'Editar' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Eliminar' })).toBeDisabled();
    expect(within(fila).getByRole('button', { name: 'Aprobar' })).toBeEnabled();
  });

  it('elimina un proceso EN_PROCESO con confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('EXTRA-001');
    const fila = screen.getByText('EXTRA-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Eliminar' }));
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/nomina/procesos-nomina-extrasalarial/p1/'),
    );
    confirmSpy.mockRestore();
  });

  it('abre los recibos y aprueba uno calculado por id', async () => {
    vi.mocked(post).mockResolvedValue({ id_nomina_extrasalarial: 'r1', estado: 'APROBADA' });
    renderPage();
    await screen.findByText('EXTRA-001');
    const fila = screen.getByText('EXTRA-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Recibos' }));
    expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
    const filaRecibo = screen.getByText('Ana Pérez').closest('tr')!;
    fireEvent.click(within(filaRecibo).getByRole('button', { name: 'Aprobar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/nomina/nominas-extrasalarial/r1/aprobar/', {}),
    );
  });

  it('muestra error al fallar el procesado', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ error: 'Estado inválido.' })));
    renderPage();
    await screen.findByText('EXTRA-001');
    const fila = screen.getByText('EXTRA-001').closest('tr')!;
    fireEvent.click(within(fila).getByRole('button', { name: 'Procesar' }));
    expect(await screen.findByText(/Estado inválido/)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });
});
