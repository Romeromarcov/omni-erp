import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/contabilidadService', () => ({
  contabilidadService: {
    getDiarios: vi.fn(),
    crearDiario: vi.fn(),
    actualizarDiario: vi.fn(),
    getPlanCuentas: vi.fn(),
    getPeriodosContables: vi.fn(),
    cerrarPeriodo: vi.fn(),
    reabrirPeriodo: vi.fn(),
    cerrarEjercicio: vi.fn(),
  },
}));

import { contabilidadService } from '../services/contabilidadService';
import DiariosContablesPage from '../pages/Contabilidad/DiariosContablesPage';

const diarioVentas = {
  id_diario: 'd-1',
  id_empresa: 'emp-1',
  codigo: 'VTA',
  nombre: 'Diario de Ventas',
  tipo: 'VENTAS',
  tipo_display: 'Ventas',
  prefijo_secuencia: 'FAC',
  siguiente_numero: 5,
  cuenta_defecto_debe: 'cta-1',
  cuenta_defecto_debe_nombre: 'Caja',
  cuenta_defecto_haber: 'cta-2',
  cuenta_defecto_haber_nombre: 'Ingresos',
  activo: true,
  fecha_creacion: '2026-06-01T10:00:00Z',
};

const cuentas = [
  {
    id_cuenta_contable: 'cta-1',
    id_empresa: 'emp-1',
    codigo_cuenta: '1.1',
    nombre_cuenta: 'Caja',
    tipo_cuenta: 'ACTIVO',
    naturaleza: 'DEUDORA',
    id_cuenta_padre: null,
    nivel: 2,
    activo: true,
    fecha_creacion: '2026-06-01T10:00:00Z',
  },
  {
    id_cuenta_contable: 'cta-2',
    id_empresa: 'emp-1',
    codigo_cuenta: '4.1',
    nombre_cuenta: 'Ingresos',
    tipo_cuenta: 'INGRESO',
    naturaleza: 'ACREEDORA',
    id_cuenta_padre: null,
    nivel: 2,
    activo: true,
    fecha_creacion: '2026-06-01T10:00:00Z',
  },
  {
    id_cuenta_contable: 'cta-3',
    id_empresa: 'emp-1',
    codigo_cuenta: '3.2',
    nombre_cuenta: 'Utilidades Acumuladas',
    tipo_cuenta: 'PATRIMONIO',
    naturaleza: 'ACREEDORA',
    id_cuenta_padre: null,
    nivel: 2,
    activo: true,
    fecha_creacion: '2026-06-01T10:00:00Z',
  },
];

const periodoCerrado = {
  id_periodo: 'per-1',
  id_empresa: 'emp-1',
  anio: 2026,
  mes: 5,
  estado: 'CERRADO',
  estado_display: 'Cerrado',
  fecha_cierre: '2026-06-01T12:00:00Z',
  cerrado_por: 'u-1',
  cerrado_por_username: 'admin',
  asiento_cierre: null,
  asiento_cierre_numero: '',
  observaciones: 'Cierre mayo',
  activo: true,
  fecha_creacion: '2026-06-01T12:00:00Z',
};

function renderPage(initialTab: 'diarios' | 'periodos' = 'diarios') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/contabilidad/diarios']}>
          <DiariosContablesPage initialTab={initialTab} />
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('DiariosContablesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(contabilidadService.getDiarios).mockResolvedValue([diarioVentas]);
    vi.mocked(contabilidadService.getPlanCuentas).mockResolvedValue(cuentas);
    vi.mocked(contabilidadService.getPeriodosContables).mockResolvedValue([periodoCerrado]);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('lista diarios contables con código, secuencia y cuentas por defecto', async () => {
    renderPage('diarios');
    expect(await screen.findByText('VTA')).toBeInTheDocument();
    expect(screen.getByText('Diario de Ventas')).toBeInTheDocument();
    expect(screen.getByText('FAC-000005')).toBeInTheDocument();
    expect(screen.getByText('Caja')).toBeInTheDocument();
    expect(screen.getByText('Ingresos')).toBeInTheDocument();
  });

  it('crea un nuevo diario contable', async () => {
    vi.mocked(contabilidadService.crearDiario).mockResolvedValue({
      ...diarioVentas,
      id_diario: 'd-2',
      codigo: 'CMP',
      nombre: 'Diario Compras',
      tipo: 'COMPRAS',
      prefijo_secuencia: 'CMP',
      siguiente_numero: 1,
    });
    const user = userEvent.setup();
    renderPage('diarios');
    await screen.findByText('VTA');

    await user.click(screen.getByRole('button', { name: 'Nuevo diario' }));
    await user.type(screen.getByLabelText(/^Código/), 'CMP');
    await user.type(screen.getByLabelText(/^Nombre/), 'Diario Compras');
    await user.type(screen.getByLabelText(/Prefijo de secuencia/), 'CMP');

    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(contabilidadService.crearDiario).toHaveBeenCalledWith({
        id_empresa: 'emp-1',
        codigo: 'CMP',
        nombre: 'Diario Compras',
        tipo: 'VARIOS',
        ambito: 'FISCAL',
        prefijo_secuencia: 'CMP',
        siguiente_numero: 1,
        cuenta_defecto_debe: null,
        cuenta_defecto_haber: null,
      });
    });
  });

  it('edita un diario existente mediante PATCH', async () => {
    vi.mocked(contabilidadService.actualizarDiario).mockResolvedValue({
      ...diarioVentas,
      nombre: 'Ventas Actualizado',
    });
    const user = userEvent.setup();
    renderPage('diarios');
    await screen.findByText('VTA');

    await user.click(screen.getByRole('button', { name: 'Editar' }));
    const nombreInput = screen.getByLabelText(/^Nombre/);
    await user.clear(nombreInput);
    await user.type(nombreInput, 'Ventas Actualizado');
    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() => {
      expect(contabilidadService.actualizarDiario).toHaveBeenCalledWith('d-1', {
        codigo: 'VTA',
        nombre: 'Ventas Actualizado',
        tipo: 'VENTAS',
        ambito: 'FISCAL',
        prefijo_secuencia: 'FAC',
        siguiente_numero: 5,
        cuenta_defecto_debe: 'cta-1',
        cuenta_defecto_haber: 'cta-2',
      });
    });
  });

  it('cambia a pestaña Períodos, cierra un período, reabre y ejecuta cierre de ejercicio', async () => {
    vi.mocked(contabilidadService.cerrarPeriodo).mockResolvedValue({
      ...periodoCerrado,
      id_periodo: 'per-2',
      mes: 6,
    });
    vi.mocked(contabilidadService.reabrirPeriodo).mockResolvedValue({
      ...periodoCerrado,
      estado: 'ABIERTO',
      estado_display: 'Abierto',
    });
    vi.mocked(contabilidadService.cerrarEjercicio).mockResolvedValue({
      anio: 2026,
      asiento_cierre: null,
      resultado_ejercicio: '350.00',
      cantidad_cuentas_saldadas: 2,
      periodos_cerrados: [periodoCerrado],
    });

    const user = userEvent.setup();
    renderPage('diarios');
    await screen.findByText('VTA');

    await user.click(screen.getByRole('tab', { name: /Períodos y Cierre Anual/ }));
    expect(await screen.findByText('2026-05')).toBeInTheDocument();

    // Cerrar período
    await user.click(screen.getByRole('button', { name: 'Cerrar período' }));
    const cerrarDialog = await screen.findByRole('dialog');
    await user.click(within(cerrarDialog).getByRole('button', { name: 'Cerrar período' }));
    await waitFor(() => {
      expect(contabilidadService.cerrarPeriodo).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    // Reabrir período cerrado
    await user.click(await screen.findByRole('button', { name: 'Reabrir' }));
    const reabrirDialog = await screen.findByRole('dialog');
    await user.type(within(reabrirDialog).getByLabelText(/Motivo de reapertura/), 'Ajuste final');
    await user.click(within(reabrirDialog).getByRole('button', { name: 'Reabrir' }));
    await waitFor(() => {
      expect(contabilidadService.reabrirPeriodo).toHaveBeenCalledWith('per-1', 'Ajuste final');
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    // Cerrar ejercicio anual
    await user.click(await screen.findByRole('button', { name: 'Cerrar ejercicio anual' }));
    const ejercicioDialog = await screen.findByRole('dialog');
    await user.click(within(ejercicioDialog).getByRole('button', { name: 'Cerrar ejercicio anual' }));
    await waitFor(() => {
      expect(contabilidadService.cerrarEjercicio).toHaveBeenCalledWith(
        expect.objectContaining({
          id_empresa: 'emp-1',
          cuenta_resultado_acumulado: 'cta-3',
        }),
      );
    });
    expect((await screen.findAllByText(/Resultado neto: 350\.00/)).length).toBeGreaterThanOrEqual(1);
  });
});
