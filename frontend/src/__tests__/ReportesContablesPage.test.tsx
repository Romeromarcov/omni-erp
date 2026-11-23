import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedbackProvider } from '../contexts/FeedbackContext';

vi.mock('../services/contabilidadService', () => ({
  contabilidadService: {
    getDiarios: vi.fn(),
    getPlanCuentas: vi.fn(),
    getContactosSelector: vi.fn(),
    listCentrosCosto: vi.fn(),
    getBalanceComprobacion: vi.fn(),
    getEstadoResultados: vi.fn(),
    getBalanceGeneral: vi.fn(),
    getLibroMayorAuxiliar: vi.fn(),
    exportarReporteBlob: vi.fn(),
  },
}));

import { contabilidadService } from '../services/contabilidadService';
import ReportesContablesPage from '../pages/Contabilidad/ReportesContablesPage';

const balanceComprobacionMock = {
  empresa_id: 'emp-1',
  fecha_desde: '2026-01-01',
  fecha_hasta: '2026-03-31',
  id_diario: null,
  diario_nombre: '',
  moneda_base: 'VES',
  moneda_base_simbolo: 'Bs.',
  incluir_equivalentes_usd: false,
  usd_disponible: false,
  tasa_usd: null,
  usd_mensaje: '',
  cuentas: [
    {
      id_cuenta_contable: 'cta-1',
      id_cuenta_padre: null,
      codigo_cuenta: '1.1.01',
      nombre_cuenta: 'Caja General',
      tipo_cuenta: 'ACTIVO',
      naturaleza: 'DEUDORA',
      nivel: 2,
      debe_inicial: '100.00',
      haber_inicial: '0.00',
      saldo_inicial: '100.00',
      saldo_inicial_deudor: '100.00',
      saldo_inicial_acreedor: '0.00',
      debe: '200.00',
      haber: '50.00',
      debe_periodo: '200.00',
      haber_periodo: '50.00',
      debe_final_acum: '300.00',
      haber_final_acum: '50.00',
      saldo: '250.00',
      saldo_final_deudor: '250.00',
      saldo_final_acreedor: '0.00',
      debe_usd: null,
      haber_usd: null,
      saldo_usd: null,
    },
  ],
  total_debe_inicial: '100.00',
  total_haber_inicial: '100.00',
  total_saldo_inicial_deudor: '100.00',
  total_saldo_inicial_acreedor: '100.00',
  total_debe: '200.00',
  total_haber: '200.00',
  total_debe_periodo: '200.00',
  total_haber_periodo: '200.00',
  total_debe_final_acum: '300.00',
  total_haber_final_acum: '300.00',
  total_saldo_final_deudor: '250.00',
  total_saldo_final_acreedor: '250.00',
  cuadrado: true,
};

const estadoResultadosMock = {
  empresa_id: 'emp-1',
  fecha_desde: '2026-01-01',
  fecha_hasta: '2026-03-31',
  moneda_base: 'VES',
  moneda_base_simbolo: 'Bs.',
  incluir_equivalentes_usd: false,
  usd_disponible: false,
  tasa_usd: null,
  usd_mensaje: '',
  ingresos: [
    {
      id_cuenta_contable: 'cta-ing',
      id_cuenta_padre: null,
      codigo_cuenta: '4.1.01',
      nombre_cuenta: 'Ventas Netas',
      tipo_cuenta: 'INGRESO',
      naturaleza: 'ACREEDORA',
      nivel: 2,
      debe: '0.00',
      haber: '500.00',
      saldo: '500.00',
    },
  ],
  costos: [],
  gastos: [
    {
      id_cuenta_contable: 'cta-gas',
      id_cuenta_padre: null,
      codigo_cuenta: '6.1.01',
      nombre_cuenta: 'Alquiler',
      tipo_cuenta: 'GASTO',
      naturaleza: 'DEUDORA',
      nivel: 2,
      debe: '150.00',
      haber: '0.00',
      saldo: '150.00',
    },
  ],
  total_ingresos: '500.00',
  total_costos: '0.00',
  total_gastos: '150.00',
  utilidad_bruta: '500.00',
  resultado_neto: '350.00',
};

const balanceGeneralMock = {
  empresa_id: 'emp-1',
  fecha_corte: '2026-03-31',
  moneda_base: 'VES',
  moneda_base_simbolo: 'Bs.',
  incluir_equivalentes_usd: false,
  usd_disponible: false,
  tasa_usd: null,
  usd_mensaje: '',
  activos: [
    {
      id_cuenta_contable: 'cta-1',
      id_cuenta_padre: null,
      codigo_cuenta: '1.1.01',
      nombre_cuenta: 'Caja General',
      tipo_cuenta: 'ACTIVO',
      naturaleza: 'DEUDORA',
      nivel: 2,
      debe: '500.00',
      haber: '0.00',
      saldo: '500.00',
    },
  ],
  pasivos: [],
  patrimonio: [
    {
      id_cuenta_contable: 'cta-cap',
      id_cuenta_padre: null,
      codigo_cuenta: '3.1.01',
      nombre_cuenta: 'Capital',
      tipo_cuenta: 'PATRIMONIO',
      naturaleza: 'ACREEDORA',
      nivel: 2,
      debe: '0.00',
      haber: '150.00',
      saldo: '150.00',
    },
  ],
  total_activos: '500.00',
  total_pasivos: '0.00',
  total_patrimonio: '150.00',
  resultado_periodo: '350.00',
  total_pasivo_patrimonio_y_resultado: '500.00',
  ecuacion_cuadrada: true,
};

const libroMayorMock = {
  empresa_id: 'emp-1',
  fecha_desde: null,
  fecha_hasta: null,
  id_cuenta_contable: null,
  cuenta_label: '',
  id_contacto: null,
  contacto_label: '',
  id_diario: null,
  diario_label: '',
  limit: 1000,
  moneda_base: 'VES',
  moneda_base_simbolo: 'Bs.',
  incluir_equivalentes_usd: false,
  usd_disponible: false,
  tasa_usd: null,
  usd_mensaje: '',
  saldo_inicial: '100.00',
  total_debe: '200.00',
  total_haber: '50.00',
  saldo_final: '250.00',
  truncado: false,
  movimientos: [
    {
      id_detalle_asiento: 'det-1',
      id_asiento: 'as-1',
      fecha_asiento: '2026-03-10',
      numero_asiento: 'AST-001',
      descripcion_asiento: 'Cobro factura',
      descripcion_detalle: 'Cobro cliente',
      id_diario: 'd-1',
      diario_codigo: 'VTA',
      diario_nombre: 'Diario Ventas',
      id_cuenta_contable: 'cta-1',
      codigo_cuenta: '1.1.01',
      nombre_cuenta: 'Caja General',
      id_contacto: 'cnt-1',
      contacto_nombre: 'Cliente Uno',
      debe: '200.00',
      haber: '0.00',
      saldo_corrido: '300.00',
    },
  ],
};

function renderPage(initialTab?: 'balance-comprobacion' | 'estado-resultados' | 'balance-general' | 'mayor-auxiliar') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MemoryRouter initialEntries={['/contabilidad/reportes']}>
          <ReportesContablesPage initialTab={initialTab} />
        </MemoryRouter>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('ReportesContablesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'emp-1');
    vi.mocked(contabilidadService.getDiarios).mockResolvedValue([
      {
        id_diario: 'd-1',
        id_empresa: 'emp-1',
        codigo: 'VTA',
        nombre: 'Diario Ventas',
        tipo: 'VENTAS',
        prefijo_secuencia: 'FV',
        siguiente_numero: 1,
        cuenta_defecto_debe: null,
        cuenta_defecto_haber: null,
        activo: true,
        fecha_creacion: '2026-01-01T00:00:00Z',
      },
    ]);
    vi.mocked(contabilidadService.getPlanCuentas).mockResolvedValue([
      {
        id_cuenta_contable: 'cta-1',
        id_empresa: 'emp-1',
        codigo_cuenta: '1.1.01',
        nombre_cuenta: 'Caja General',
        tipo_cuenta: 'ACTIVO',
        naturaleza: 'DEUDORA',
        id_cuenta_padre: null,
        nivel: 2,
        activo: true,
        fecha_creacion: '2026-01-01T00:00:00Z',
      },
    ]);
    vi.mocked(contabilidadService.getContactosSelector).mockResolvedValue([
      { id_contacto: 'cnt-1', nombre_completo: 'Cliente Uno', rif: 'J-12345678-9' },
    ]);
    vi.mocked(contabilidadService.listCentrosCosto).mockResolvedValue([
      {
        id_centro_costo: 'cc-1',
        id_empresa: 'emp-1',
        codigo: 'CC-LOG',
        nombre: 'Logística',
        tipo: 'LOGISTICA',
        id_padre: null,
        activo: true,
        fecha_creacion: '2026-01-01T00:00:00Z',
      },
    ]);
    vi.mocked(contabilidadService.getBalanceComprobacion).mockResolvedValue(balanceComprobacionMock);
    vi.mocked(contabilidadService.getEstadoResultados).mockResolvedValue(estadoResultadosMock);
    vi.mocked(contabilidadService.getBalanceGeneral).mockResolvedValue(balanceGeneralMock);
    vi.mocked(contabilidadService.getLibroMayorAuxiliar).mockResolvedValue(libroMayorMock);
    vi.mocked(contabilidadService.exportarReporteBlob).mockResolvedValue(new Blob(['ok']));
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('renderiza los 4 tabs de reportes financieros con datos exactos y ecuación patrimonial', async () => {
    const user = userEvent.setup();
    renderPage();

    // Tab 1: Balance de Comprobación
    expect(await screen.findByText('Caja General')).toBeInTheDocument();
    expect(screen.getByText('250.00')).toBeInTheDocument();

    // Tab 2: Estado de Resultados
    await user.click(screen.getByRole('tab', { name: 'Estado de Resultados' }));
    expect(await screen.findByText('Ventas Netas')).toBeInTheDocument();
    expect(screen.getByText('350.00')).toBeInTheDocument();

    // Tab 3: Balance General
    await user.click(screen.getByRole('tab', { name: 'Balance General' }));
    expect(await screen.findByText(/Ecuación patrimonial cuadrada/)).toBeInTheDocument();
    expect(screen.getByText('Capital')).toBeInTheDocument();

    // Tab 4: Libro Mayor Auxiliar
    await user.click(screen.getByRole('tab', { name: 'Libro Mayor Auxiliar' }));
    expect(await screen.findByText('AST-001')).toBeInTheDocument();
    expect(screen.getByText('Cliente Uno')).toBeInTheDocument();
    expect(screen.getByText('300.00')).toBeInTheDocument();
  });

  it('activa switch de equivalentes USD, muestra advertencia si no hay tasa o columnas USD si hay tasa', async () => {
    vi.mocked(contabilidadService.getBalanceComprobacion)
      .mockResolvedValueOnce(balanceComprobacionMock)
      .mockResolvedValueOnce({
        ...balanceComprobacionMock,
        incluir_equivalentes_usd: true,
        usd_disponible: true,
        tasa_usd: '40.00000000',
        total_debe_usd: '5.00',
        total_haber_usd: '5.00',
        cuentas: [
          {
            ...balanceComprobacionMock.cuentas[0],
            debe_usd: '5.00',
            haber_usd: '1.25',
            saldo_usd: '6.25',
          },
        ],
      })
      .mockResolvedValueOnce({
        ...balanceComprobacionMock,
        incluir_equivalentes_usd: true,
        usd_disponible: false,
        tasa_usd: null,
        usd_mensaje: 'Sin tasa USD disponible',
      });

    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Caja General');

    // Activar USD con tasa disponible
    await user.click(screen.getByRole('switch', { name: /Mostrar equivalentes USD/ }));
    expect(await screen.findByText(/1 USD = 40\.00000000 VES/)).toBeInTheDocument();
    expect(screen.getByText('6.25')).toBeInTheDocument();

    // Re-consultar sin tasa disponible -> advertencia explícita
    await user.type(screen.getByLabelText('Desde'), '2026-02-01');
    expect(await screen.findByText('Sin tasa USD disponible')).toBeInTheDocument();
  });

  it('descarga exportación CSV y PDF vía Blob', async () => {
    const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
    const revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Caja General');

    await user.click(screen.getByRole('button', { name: 'Exportar CSV' }));
    await waitFor(() => {
      expect(contabilidadService.exportarReporteBlob).toHaveBeenCalledWith(
        'balance-comprobacion',
        'csv',
        expect.objectContaining({ empresa_id: 'emp-1' }),
      );
    });

    await user.click(screen.getByRole('button', { name: 'Exportar PDF' }));
    await waitFor(() => {
      expect(contabilidadService.exportarReporteBlob).toHaveBeenCalledWith(
        'balance-comprobacion',
        'pdf',
        expect.objectContaining({ empresa_id: 'emp-1' }),
      );
    });

    expect(createObjectUrlSpy).toHaveBeenCalledTimes(2);
    expect(clickSpy).toHaveBeenCalledTimes(2);
    expect(revokeObjectUrlSpy).toHaveBeenCalledTimes(2);

    createObjectUrlSpy.mockRestore();
    revokeObjectUrlSpy.mockRestore();
    clickSpy.mockRestore();
  });

  it('permite filtrar por Libro (ámbito dual), Moneda trimonetaria y Centro de costo', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Caja General');

    await user.click(screen.getByRole('combobox', { name: 'Libro' }));
    await user.click(await screen.findByRole('option', { name: 'Solo Gerencial' }));

    await user.click(screen.getByRole('combobox', { name: 'Moneda' }));
    await user.click(await screen.findByRole('option', { name: 'Referencia (USDT)' }));

    await user.click(screen.getByRole('combobox', { name: 'Centro de costo' }));
    await user.click(await screen.findByRole('option', { name: /CC-LOG — Logística/ }));

    await waitFor(() => {
      expect(contabilidadService.getBalanceComprobacion).toHaveBeenLastCalledWith(
        expect.objectContaining({
          empresa_id: 'emp-1',
          ambito: 'GERENCIAL',
          moneda: 'REFERENCIA',
          id_centro_costo: 'cc-1',
        }),
      );
    });
  });
});
