import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../../../contexts/FeedbackContext';
import {
  conciliacionPagosService,
  type EstadoConciliacionContacto,
} from '../../../services/conciliacionPagosService';
import ConciliacionContactoDialog from '../ConciliacionContactoDialog';

vi.mock('../../../services/conciliacionPagosService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../services/conciliacionPagosService')
  >('../../../services/conciliacionPagosService');
  return {
    ...actual,
    conciliacionPagosService: {
      obtenerEstadoConciliacionContacto: vi.fn(),
      sugerirDistribucionPago: vi.fn(),
      conciliarPagoDocumentos: vi.fn(),
      crearAsignacionPago: vi.fn(),
      revertirAsignacionPago: vi.fn(),
      listarAsignacionesPago: vi.fn(),
    },
  };
});

const mockedService = vi.mocked(conciliacionPagosService);

const ESTADO_MOCK: EstadoConciliacionContacto = {
  contacto: {
    id_contacto: '11111111-1111-1111-1111-111111111111',
    nombre: 'Comercial Alpha C.A.',
    rif: 'J-12345678-9',
    es_cliente: true,
    es_proveedor: true,
  },
  saldo_a_favor: {
    total_por_moneda: {
      USD: {
        moneda_id: '22222222-2222-2222-2222-222222222222',
        codigo_iso: 'USD',
        simbolo: '$',
        INGRESO: '0.3500',
        EGRESO: '0.0000',
        cantidad_pagos: 1,
      },
    },
    total_pagos_con_saldo: 1,
  },
  pagos_disponibles: [
    {
      id_pago: '33333333-3333-3333-3333-333333333333',
      fecha_pago: '2026-04-10T12:00:00Z',
      tipo_operacion: 'INGRESO',
      monto: '1.0000',
      saldo_disponible: '0.3500',
      moneda_codigo: 'USD',
      referencia: 'TRF-ANTICIPO-01',
      tasa: '1.0000',
    },
  ],
  obligaciones_abiertas: [
    {
      tipo_documento: 'FACTURA_VENTA',
      id_documento: '44444444-4444-4444-4444-444444444444',
      numero_documento: 'FV-0001',
      fecha_emision: '2026-04-01',
      fecha_vencimiento: '2026-04-15',
      monto_total: '10.0000',
      saldo_pendiente: '0.5000',
      moneda_codigo: 'USD',
      estado: 'EMITIDA',
    },
    {
      tipo_documento: 'CUENTA_POR_COBRAR',
      id_documento: '77',
      numero_documento: 'CXC-0077',
      fecha_emision: '2026-04-02',
      fecha_vencimiento: '2026-04-20',
      monto_total: '5.00',
      saldo_pendiente: '0.40',
      moneda_codigo: 'USD',
      estado: 'pendiente',
    },
  ],
  asignaciones_activas: [
    {
      id_asignacion: '55555555-5555-5555-5555-555555555555',
      id_empresa: '66666666-6666-6666-6666-666666666666',
      id_contacto: '11111111-1111-1111-1111-111111111111',
      contacto_nombre: 'Comercial Alpha C.A.',
      id_pago: '33333333-3333-3333-3333-333333333333',
      pago_referencia: 'TRF-ANTICIPO-01',
      tipo_documento: 'FACTURA_VENTA',
      id_documento: '44444444-4444-4444-4444-444444444444',
      id_cxc: null,
      id_cxp: null,
      id_factura_venta: '44444444-4444-4444-4444-444444444444',
      id_factura_compra: null,
      id_abono_cxc: null,
      id_abono_cxp: null,
      monto_asignado_pago: '0.6500',
      monto_asignado_documento: '0.6500',
      id_moneda_documento: '22222222-2222-2222-2222-222222222222',
      moneda_documento_codigo: 'USD',
      tasa_aplicada: '1.00000000',
      diferencia_cambiaria: '0.0000',
      tipo_diferencia: 'NINGUNA',
      estado: 'ACTIVA',
      fecha_aplicacion: '2026-04-10T12:05:00Z',
      fecha_reversion: null,
      motivo_reversion: null,
      id_asiento: null,
      id_asiento_reversion: null,
      id_usuario_registro: null,
      referencia_externa: '',
      activo: true,
      fecha_creacion: '2026-04-10T12:05:00Z',
    },
  ],
};

function renderDialog(onSuccess = vi.fn(), onClose = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <ConciliacionContactoDialog
          open
          contactoId={ESTADO_MOCK.contacto.id_contacto}
          tipoOperacionFiltro="INGRESO"
          onClose={onClose}
          onSuccess={onSuccess}
        />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('ConciliacionContactoDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedService.obtenerEstadoConciliacionContacto.mockResolvedValue(ESTADO_MOCK);
  });

  it('calcula totales exactos con decimal.js (0.1 + 0.2 = 0.30) y valida excesos', async () => {
    const user = userEvent.setup();
    renderDialog();

    await screen.findByText(/Comercial Alpha C\.A\./i);
    expect(screen.getByText('FV-0001')).toBeInTheDocument();
    expect(screen.getByText('CXC-0077')).toBeInTheDocument();

    const inputFv = screen.getByLabelText('Monto para FV-0001');
    const inputCxc = screen.getByLabelText('Monto para CXC-0077');

    // 0.1 + 0.2 en decimal.js == 0.30 exacto y restante == 0.05 (de 0.35 disponible)
    await user.type(inputFv, '0.1');
    await user.type(inputCxc, '0.2');

    expect(screen.getByText(/0\.30\s*USD/)).toBeInTheDocument();
    expect(screen.getByText(/0\.05\s*USD/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /aplicar conciliación/i })).toBeEnabled();

    // Superar saldo pendiente de la factura (0.60 > 0.50) muestra error y deshabilita submit
    await user.clear(inputFv);
    await user.type(inputFv, '0.60');
    expect(screen.getByText(/supera el saldo/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /aplicar conciliación/i })).toBeDisabled();

    // Valor negativo tampoco es permitido
    await user.clear(inputFv);
    await user.type(inputFv, '-1');
    expect(screen.getByText(/debe ser mayor a 0/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /aplicar conciliación/i })).toBeDisabled();
  });

  it('distribuye con FIFO, muestra advertencias sin tasa y aplica enviando Idempotency-Key', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    mockedService.sugerirDistribucionPago.mockResolvedValue({
      pago_id: ESTADO_MOCK.pagos_disponibles[0].id_pago,
      saldo_disponible: '0.3500',
      propuestas: [
        {
          tipo_documento: 'FACTURA_VENTA',
          id_documento: '44444444-4444-4444-4444-444444444444',
          referencia: 'FV-0001',
          fecha_emision: '2026-04-01',
          fecha_vencimiento: '2026-04-15',
          moneda_documento: '22222222-2222-2222-2222-222222222222',
          moneda_documento_codigo: 'USD',
          saldo_pendiente_documento: '0.5000',
          tasa_aplicada: '1.00000000',
          monto_asignado_pago: '0.3500',
          monto_asignado_documento: '0.3500',
        },
      ],
      total_a_aplicar: '0.3500',
      saldo_a_favor_resultante: '0.0000',
      omitidas_sin_tasa: [
        {
          tipo_documento: 'CUENTA_POR_COBRAR',
          id_documento: '99',
          moneda_codigo: 'EUR',
          motivo: 'Sin tasa activa',
        },
      ],
    });
    mockedService.conciliarPagoDocumentos.mockResolvedValue({
      pago_id: ESTADO_MOCK.pagos_disponibles[0].id_pago,
      saldo_disponible: '0.0000',
      asignaciones: ESTADO_MOCK.asignaciones_activas,
    });

    renderDialog(onSuccess);
    await screen.findByText('FV-0001');

    await user.click(screen.getByRole('button', { name: /distribuir fifo/i }));

    await waitFor(() => {
      expect(mockedService.sugerirDistribucionPago).toHaveBeenCalledWith(
        '33333333-3333-3333-3333-333333333333',
      );
    });
    expect(screen.getByText(/documentos omitidos en fifo/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Monto para FV-0001')).toHaveValue('0.3500');

    await user.type(
      screen.getByLabelText(/descripción o nota de conciliación/i),
      'Conciliación FIFO prueba',
    );
    await user.click(screen.getByRole('button', { name: /aplicar conciliación/i }));

    await waitFor(() => {
      expect(mockedService.conciliarPagoDocumentos).toHaveBeenCalledTimes(1);
    });
    const [pagoId, payload, idempKey] = mockedService.conciliarPagoDocumentos.mock.calls[0];
    expect(pagoId).toBe('33333333-3333-3333-3333-333333333333');
    expect(payload).toEqual({
      asignaciones: [
        {
          tipo_documento: 'FACTURA_VENTA',
          id_documento: '44444444-4444-4444-4444-444444444444',
          monto_asignado_pago: '0.3500',
          tasa_aplicada: '1.00000000',
        },
      ],
      descripcion: 'Conciliación FIFO prueba',
      generar_asiento: true,
    });
    expect(typeof idempKey).toBe('string');
    expect((idempKey ?? '').length).toBeGreaterThanOrEqual(8);
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('permite revertir una asignación activa desde la pestaña correspondiente', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    mockedService.revertirAsignacionPago.mockResolvedValue({
      ...ESTADO_MOCK.asignaciones_activas[0],
      estado: 'REVERTIDA',
      motivo_reversion: 'Error de captura',
    });

    renderDialog(onSuccess);
    await screen.findByText('FV-0001');

    await user.click(screen.getByRole('tab', { name: /asignaciones activas \(1\)/i }));
    const motivoInput = await screen.findByLabelText(
      'Motivo reversión 55555555-5555-5555-5555-555555555555',
    );
    await user.type(motivoInput, 'Error de captura');
    await user.click(screen.getByRole('button', { name: /revertir/i }));

    await waitFor(() => {
      expect(mockedService.revertirAsignacionPago).toHaveBeenCalledTimes(1);
    });
    const [asigId, motivo, idempKey] = mockedService.revertirAsignacionPago.mock.calls[0];
    expect(asigId).toBe('55555555-5555-5555-5555-555555555555');
    expect(motivo).toBe('Error de captura');
    expect(typeof idempKey).toBe('string');
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });
});
