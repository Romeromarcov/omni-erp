import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/cxcLubrikcaService', () => ({
  cxcLubrikcaService: {
    listDescuentosMarca: vi.fn(),
    crearDescuentoMarca: vi.fn(),
    actualizarDescuentoMarca: vi.fn(),
    eliminarDescuentoMarca: vi.fn(),
    listDescuentosBcv: vi.fn(),
    crearDescuentoBcv: vi.fn(),
    actualizarDescuentoBcv: vi.fn(),
    eliminarDescuentoBcv: vi.fn(),
    patchDescuentoBcv: vi.fn(),
    patchDescuentoMarca: vi.fn(),
    listPromociones: vi.fn(),
    crearPromocion: vi.fn(),
    actualizarPromocion: vi.fn(),
    patchPromocion: vi.fn(),
    eliminarPromocion: vi.fn(),
    listReglasRecurrencia: vi.fn(),
    crearReglaRecurrencia: vi.fn(),
    actualizarReglaRecurrencia: vi.fn(),
    patchReglaRecurrencia: vi.fn(),
    eliminarReglaRecurrencia: vi.fn(),
    listFeriados: vi.fn(),
    crearFeriado: vi.fn(),
    actualizarFeriado: vi.fn(),
    patchFeriado: vi.fn(),
    eliminarFeriado: vi.fn(),
    listMetodosPago: vi.fn(),
    crearMetodoPago: vi.fn(),
    actualizarMetodoPago: vi.fn(),
    patchMetodoPago: vi.fn(),
    eliminarMetodoPago: vi.fn(),
    listConfigConciliacion: vi.fn(),
    crearConfigConciliacion: vi.fn(),
    actualizarConfigConciliacion: vi.fn(),
    patchConfigConciliacion: vi.fn(),
    eliminarConfigConciliacion: vi.fn(),
  },
}));

import { cxcLubrikcaService } from '../services/cxcLubrikcaService';
import ConfigMotorPage from '../pages/CxcLubrikca/ConfigMotorPage';

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FeedbackProvider>
          <ConfigMotorPage />
        </FeedbackProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const descuento = {
  id: 1,
  marca: 'Castrol',
  categoria: 'Lubricantes',
  tipo_descuento: 'contado',
  porcentaje: '0.030000',
  vigencia_desde: '2026-01-01',
  vigencia_hasta: null,
  activo: true,
};

describe('ConfigMotorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cxcLubrikcaService.listDescuentosMarca).mockResolvedValue([descuento]);
    vi.mocked(cxcLubrikcaService.listDescuentosBcv).mockResolvedValue([]);
    vi.mocked(cxcLubrikcaService.listPromociones).mockResolvedValue([]);
    vi.mocked(cxcLubrikcaService.listReglasRecurrencia).mockResolvedValue([]);
    vi.mocked(cxcLubrikcaService.listFeriados).mockResolvedValue([]);
    vi.mocked(cxcLubrikcaService.listMetodosPago).mockResolvedValue([]);
    vi.mocked(cxcLubrikcaService.listConfigConciliacion).mockResolvedValue([]);
  });

  afterEach(() => cleanup());

  it('lista los descuentos de la primera pestaña con porcentaje en %', async () => {
    renderPage();
    expect(await screen.findByText('Castrol')).toBeInTheDocument();
    expect(screen.getByText('Lubricantes')).toBeInTheDocument();
    expect(screen.getByText('3%')).toBeInTheDocument();
  });

  it('valida campos requeridos antes de crear', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('button', { name: /nuevo/i }));
    // marca/categoria por defecto son '*', así que vaciamos porcentaje deja desde requerido
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /guardar/i }));
    expect(await screen.findByText(/el porcentaje es obligatorio/i)).toBeInTheDocument();
    expect(cxcLubrikcaService.crearDescuentoMarca).not.toHaveBeenCalled();
  });

  it('crea un descuento enviando vigencia_hasta como null cuando está vacía', async () => {
    vi.mocked(cxcLubrikcaService.crearDescuentoMarca).mockResolvedValue(descuento);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('button', { name: /nuevo/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/porcentaje/i), '0.05');
    await user.type(within(dialog).getByLabelText(/vigencia desde/i), '2026-02-01');
    await user.click(within(dialog).getByRole('button', { name: /guardar/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.crearDescuentoMarca).toHaveBeenCalledWith(
        expect.objectContaining({
          marca: '*',
          categoria: '*',
          tipo_descuento: 'contado',
          porcentaje: '0.05',
          vigencia_desde: '2026-02-01',
          vigencia_hasta: null,
        }),
      );
    });
  });

  it('abre el diálogo en modo edición con los valores de la fila', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('button', { name: /editar/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/editar registro/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/marca/i)).toHaveValue('Castrol');
  });

  it('elimina un registro (soft-delete)', async () => {
    vi.mocked(cxcLubrikcaService.eliminarDescuentoMarca).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('button', { name: /eliminar/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.eliminarDescuentoMarca).toHaveBeenCalledWith(1);
    });
  });

  it('cambia de pestaña a Tolerancias y muestra su lista', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('tab', { name: /tolerancias conciliación/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.listConfigConciliacion).toHaveBeenCalled();
    });
    expect(await screen.findByText(/no hay registros configurados/i)).toBeInTheDocument();
  });

  it('muestra un error general cuando el guardado falla en el backend', async () => {
    vi.mocked(cxcLubrikcaService.crearDescuentoMarca).mockRejectedValue(
      new Error(JSON.stringify({ detail: 'Vigencia inválida' })),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('button', { name: /nuevo/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/porcentaje/i), '0.05');
    await user.type(within(dialog).getByLabelText(/vigencia desde/i), '2026-02-01');
    await user.click(within(dialog).getByRole('button', { name: /guardar/i }));
    expect(await screen.findByText(/vigencia inválida/i)).toBeInTheDocument();
  });

  it('crea un método de pago con switches y selects (toggle es_contado)', async () => {
    vi.mocked(cxcLubrikcaService.listMetodosPago).mockResolvedValue([]);
    vi.mocked(cxcLubrikcaService.crearMetodoPago).mockResolvedValue({
      id: 1,
      codigo: 'ZELLE',
      nombre: 'Zelle',
      moneda: 'USD',
      tipo_tasa: 'BCV',
      es_contado: true,
      activo: true,
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('tab', { name: /métodos de pago/i }));
    await screen.findByText(/no hay registros configurados/i);
    await user.click(screen.getByRole('button', { name: /nuevo/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/código/i), 'ZELLE');
    await user.type(within(dialog).getByLabelText(/nombre/i), 'Zelle');
    // Activa el switch "Es contado".
    await user.click(within(dialog).getByLabelText(/es contado/i));
    await user.click(within(dialog).getByRole('button', { name: /guardar/i }));
    await waitFor(() => {
      expect(cxcLubrikcaService.crearMetodoPago).toHaveBeenCalledWith(
        expect.objectContaining({
          codigo: 'ZELLE',
          nombre: 'Zelle',
          moneda: 'USD',
          tipo_tasa: 'BCV',
          es_contado: true,
        }),
      );
    });
  });

  it('valida que vigencia_hasta no sea anterior a vigencia_desde', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Castrol');
    await user.click(screen.getByRole('button', { name: /nuevo/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/porcentaje/i), '0.05');
    await user.type(within(dialog).getByLabelText(/vigencia desde/i), '2026-05-01');
    await user.type(within(dialog).getByLabelText(/vigencia hasta/i), '2026-01-01');
    await user.click(within(dialog).getByRole('button', { name: /guardar/i }));
    expect(await screen.findByText(/mayor o igual a la fecha desde/i)).toBeInTheDocument();
    expect(cxcLubrikcaService.crearDescuentoMarca).not.toHaveBeenCalled();
  });
});
