import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

import type {
  MetodoPago, Moneda, CajaVirtual, NotaCredito, CuentaBancaria, Datafono,
} from '../components/Pedidos/types';
import { FeedbackContext } from '../contexts/feedbackTypes';
import type { FeedbackContextValue } from '../contexts/feedbackTypes';

// ── Mock del hook de datos: el modal se prueba con datos controlados ─────────
interface HookData {
  metodos: MetodoPago[];
  monedas: Moneda[];
  cajas: CajaVirtual[];
  tasaBCV: number;
  toleranciaPositiva: number;
  permitirNegativas: boolean;
  notasCredito: NotaCredito[];
  cuentasBancarias: CuentaBancaria[];
  datafonos: Datafono[];
  cajaFisicaActual: { id_caja: string } | null;
  tasaBCVLoading: boolean;
  tasaBCVError: Error | null;
  tasaBCVNoDisponible: boolean;
}

const METODOS: MetodoPago[] = [
  { id_metodo_pago: 'efe', nombre_metodo: 'Efectivo', tipo_metodo: 'efectivo' },
  { id_metodo_pago: 'tra', nombre_metodo: 'Transferencia', tipo_metodo: 'transferencia' },
  { id_metodo_pago: 'tar', nombre_metodo: 'Tarjeta', tipo_metodo: 'tarjeta_debito' },
];
const MONEDAS: Moneda[] = [
  { id_moneda: 'usd', nombre: 'Dólar', codigo_iso: 'USD', es_base: true },
  { id_moneda: 'ves', nombre: 'Bolívar', codigo_iso: 'VES', es_pais: true },
];
const CAJAS: CajaVirtual[] = [
  { id_caja: 'cv1', nombre: 'Caja Bs', moneda: 'VES', moneda_codigo_iso: 'VES', id_moneda: 'ves', activa: true },
];
const CUENTAS: CuentaBancaria[] = [
  {
    id_cuenta_bancaria: 'cb1', nombre_cuenta: 'Cta USD', numero_cuenta: '0102-1234',
    id_moneda: 'usd', id_banco: 'b1', nombre_banco: 'BNC',
    metodos_pago: ['tra'], monedas: ['usd'],
  },
];
const DATAFONOS: Datafono[] = [
  {
    id_datafono: 'dt1', nombre: 'Punto 1', id_moneda: 'ves', id_cuenta_bancaria: 'cb1',
    metodos_pago: ['tar'], monedas: ['ves'],
  },
];

let hookData: HookData;

function baseHookData(): HookData {
  return {
    metodos: METODOS,
    monedas: MONEDAS,
    cajas: CAJAS,
    tasaBCV: 10,
    toleranciaPositiva: 0.5,
    permitirNegativas: true,
    notasCredito: [],
    cuentasBancarias: CUENTAS,
    datafonos: DATAFONOS,
    cajaFisicaActual: { id_caja: 'cf1' },
    tasaBCVLoading: false,
    tasaBCVError: null,
    tasaBCVNoDisponible: false,
  };
}

vi.mock('../components/Pedidos/useModalPagoData', () => ({
  useModalPagoData: () => hookData,
}));

import ModalPago from '../components/Pedidos/ModalPago';

const snackbar = {
  notify: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(),
};
const feedback: FeedbackContextValue = { snackbar, confirm: vi.fn() };

function renderModal(overrides: Partial<React.ComponentProps<typeof ModalPago>> = {}) {
  const props: React.ComponentProps<typeof ModalPago> = {
    open: true,
    monto: 100,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    empresaId: 'emp-1',
    ...overrides,
  };
  render(
    <FeedbackContext.Provider value={feedback}>
      <ModalPago {...props} />
    </FeedbackContext.Provider>,
  );
  return props;
}

// Los Select de MUI no exponen nombre accesible aquí; se ubican por orden en el
// DOM: [0] Tipo de Operación, [1] Método, [2] Moneda.
const combos = () => screen.getAllByRole('combobox');

async function seleccionarMetodoYMoneda(metodo: string, moneda: string, monto: string) {
  const user = userEvent.setup();
  await user.click(combos()[1]);
  await user.click(await screen.findByRole('option', { name: metodo }));
  await user.click(combos()[2]);
  const opciones = await screen.findAllByRole('option', { name: moneda });
  await user.click(opciones[0]);
  fireEvent.change(screen.getByLabelText(/^monto$/i), { target: { value: monto } });
  return user;
}

beforeEach(() => {
  hookData = baseHookData();
  vi.clearAllMocks();
});

afterEach(() => cleanup());

describe('ModalPago — render básico', () => {
  it('no renderiza nada cuando open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByText(/registrar pago/i)).not.toBeInTheDocument();
  });

  it('detecta INGRESO para documentos de venta y lo informa', () => {
    renderModal({ tipoDocumento: 'PEDIDO' });
    expect(screen.getByText(/detectado automáticamente del documento: PEDIDO/i)).toBeInTheDocument();
    expect(combos()[0]).toHaveTextContent('INGRESO');
  });

  it('detecta EGRESO para documentos de gasto', () => {
    renderModal({ tipoDocumento: 'GASTO' });
    expect(combos()[0]).toHaveTextContent('EGRESO');
  });

  it('deshabilita "Confirmar pagos" sin pagos ni notas de crédito', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /confirmar pagos/i })).toBeDisabled();
  });
});

describe('ModalPago — agregar pagos y conversiones de dinero', () => {
  it('agrega un pago en moneda país convirtiendo a base por la tasa (1000 VES / 10 = 100 USD)', async () => {
    const user = userEvent.setup();
    const props = renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Efectivo', 'VES', '1000');
    // El efecto de auto-selección asigna la caja virtual compatible (VES).
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    expect(snackbar.warning).not.toHaveBeenCalled();
    expect(await screen.findByText(/Efectivo –/)).toBeInTheDocument();
    expect(screen.getByText(/Monto: VES 1000\.00 \| Base: USD 100\.00 \| País: VES 1000\.00/)).toBeInTheDocument();

    // Saldo en 0 → confirmar entrega los pagos con sus montos convertidos.
    await user.click(screen.getByRole('button', { name: /confirmar pagos/i }));
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
    const [pagos, vueltos, notas] = (props.onConfirm as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(pagos).toHaveLength(1);
    expect(pagos[0]).toMatchObject({
      id_metodo_pago: 'efe',
      id_moneda: 'ves',
      moneda: 'VES',
      monto: 1000,
      monto_base: 100,
      monto_pais: 1000,
      id_caja_virtual: 'cv1',
    });
    expect(vueltos).toBeUndefined();
    expect(notas).toEqual([]);
  });

  it('agrega un pago en moneda base 1:1 (USD no se reconvierte)', async () => {
    const user = userEvent.setup();
    renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Transferencia', 'USD', '100');
    // Auto-selección: la cuenta bancaria compatible con (tra, usd).
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    expect(snackbar.warning).not.toHaveBeenCalled();
    expect(screen.getByText(/Monto: USD 100\.00 \| Base: USD 100\.00 \| País: VES 1000\.00/)).toBeInTheDocument();
  });

  it('permite eliminar un pago agregado', async () => {
    const user = userEvent.setup();
    renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Efectivo', 'VES', '1000');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    expect(screen.getByText(/Efectivo –/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /delete/i }));
    expect(screen.queryByText(/Efectivo –/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirmar pagos/i })).toBeDisabled();
  });
});

describe('ModalPago — validaciones de entidad financiera', () => {
  it('exige caja virtual para pagos en efectivo cuando no hay auto-selección posible', async () => {
    // Sin datáfonos el efecto de auto-selección se corta y no asigna caja.
    hookData = { ...baseHookData(), datafonos: [] };
    const user = userEvent.setup();
    const props = renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Efectivo', 'VES', '1000');
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    expect(snackbar.warning).toHaveBeenCalledWith(
      'Para pagos en efectivo, debe seleccionar una caja virtual.',
    );
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it('exige cuenta bancaria para transferencias cuando no hay auto-selección posible', async () => {
    hookData = { ...baseHookData(), datafonos: [] };
    const user = userEvent.setup();
    renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Transferencia', 'USD', '100');
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    expect(snackbar.warning).toHaveBeenCalledWith(
      'Para este método de pago, debe seleccionar una cuenta bancaria.',
    );
  });

  it('exige datáfono para pagos con tarjeta cuando no hay auto-selección posible', async () => {
    hookData = { ...baseHookData(), cuentasBancarias: [] };
    const user = userEvent.setup();
    renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Tarjeta', 'USD', '100');
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    expect(snackbar.warning).toHaveBeenCalledWith(
      'Para pagos con tarjeta, debe seleccionar un datáfono.',
    );
  });
});

describe('ModalPago — tolerancia de diferencias', () => {
  it('bloquea la confirmación cuando el saldo excede la tolerancia positiva', async () => {
    const user = userEvent.setup();
    const props = renderModal({ monto: 100 });

    // Solo 50 USD pagados de 100 → diferencia +50 > tolerancia 0.5.
    await seleccionarMetodoYMoneda('Transferencia', 'USD', '50');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await user.click(screen.getByRole('button', { name: /confirmar pagos/i }));

    expect(snackbar.warning).toHaveBeenCalledWith(
      expect.stringContaining('excede la tolerancia configurada (0.50)'),
    );
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it('acepta una diferencia negativa (sobrepago) cuando permitirNegativas=true', async () => {
    const user = userEvent.setup();
    const props = renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Transferencia', 'USD', '120');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await user.click(screen.getByRole('button', { name: /confirmar pagos/i }));

    expect(props.onConfirm).toHaveBeenCalledTimes(1);
  });

  it('rechaza el sobrepago cuando permitirNegativas=false', async () => {
    hookData = { ...baseHookData(), permitirNegativas: false };
    const user = userEvent.setup();
    const props = renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Transferencia', 'USD', '120');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    await user.click(screen.getByRole('button', { name: /confirmar pagos/i }));

    expect(props.onConfirm).not.toHaveBeenCalled();
    expect(snackbar.warning).toHaveBeenCalled();
  });
});

describe('ModalPago — vuelto', () => {
  it('ofrece configurar vuelto cuando hay sobrepago y lo incluye en la confirmación', async () => {
    const user = userEvent.setup();
    const props = renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Transferencia', 'USD', '150');
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    // Sobrepago de 50 USD → sección de vuelto visible.
    expect(screen.getByText(/Vuelto disponible: USD 50\.00/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /configurar vuelto/i }));

    // El vuelto por defecto sale en moneda país con la tasa BCV.
    const seccionVuelto = screen.getByText(/entregar vuelto en/i).parentElement as HTMLElement;
    expect(within(seccionVuelto).getByRole('combobox')).toHaveTextContent('VES');

    await user.click(screen.getByRole('button', { name: /confirmar pagos/i }));
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
    const [, vueltos] = (props.onConfirm as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(vueltos).toHaveLength(1);
    expect(vueltos[0]).toMatchObject({
      id_metodo_pago: 'efectivo',
      id_moneda: 'VES',
      tasa: 10,
      monto: 5, // 50 USD disponibles / tasa de vuelto 10 (comportamiento actual)
      referencia: 'Vuelto automático',
    });
  });

  it('no ofrece vuelto sin sobrepago', async () => {
    const user = userEvent.setup();
    renderModal({ monto: 100 });

    await seleccionarMetodoYMoneda('Transferencia', 'USD', '100');
    await user.click(screen.getByRole('button', { name: /agregar/i }));

    expect(screen.queryByText(/vuelto disponible/i)).not.toBeInTheDocument();
  });
});

describe('ModalPago — notas de crédito', () => {
  const NC: NotaCredito = {
    id_nota_credito: 'nc-1',
    numero_nota: 'NC-100',
    monto_disponible: 100,
    id_moneda: 'usd',
    fecha_emision: '2026-01-01T00:00:00Z',
  };

  it('permite pagar el documento solo con una nota de crédito en moneda base', async () => {
    hookData = { ...baseHookData(), notasCredito: [NC] };
    const user = userEvent.setup();
    const props = renderModal({ monto: 100, idCliente: 'cli-1' });

    expect(screen.getByText(/notas de crédito disponibles/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /aplicar/i }));
    expect(screen.getByText(/Total aplicado: USD 100\.00/)).toBeInTheDocument();

    // NC de 100 sobre documento de 100 → saldo 0 y el botón se habilita sin pagos.
    const confirmar = screen.getByRole('button', { name: /confirmar pagos/i });
    expect(confirmar).toBeEnabled();
    await user.click(confirmar);

    const [pagos, , notas] = (props.onConfirm as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(pagos).toEqual([]);
    expect(notas).toEqual([NC]);
  });

  it('quita la nota al des-seleccionarla y vuelve a bloquear la confirmación', async () => {
    hookData = { ...baseHookData(), notasCredito: [NC] };
    const user = userEvent.setup();
    renderModal({ monto: 100, idCliente: 'cli-1' });

    await user.click(screen.getByRole('button', { name: /aplicar/i }));
    await user.click(screen.getByRole('button', { name: /quitar/i }));

    expect(screen.queryByText(/total aplicado/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirmar pagos/i })).toBeDisabled();
  });
});

describe('ModalPago — tasa BCV no disponible', () => {
  it('muestra el error de tasa y deshabilita la confirmación', async () => {
    hookData = {
      ...baseHookData(),
      tasaBCV: 1,
      tasaBCVError: new Error('BCV caído'),
      tasaBCVNoDisponible: true,
    };
    const user = userEvent.setup();
    const props = renderModal({ monto: 100 });

    expect(screen.getByText(/no se pudo cargar la tasa bcv/i)).toBeInTheDocument();

    // Aunque haya pagos cargados, el botón queda deshabilitado.
    await seleccionarMetodoYMoneda('Transferencia', 'USD', '100');
    await user.click(screen.getByRole('button', { name: /agregar/i }));
    expect(screen.getByRole('button', { name: /confirmar pagos/i })).toBeDisabled();
    expect(props.onConfirm).not.toHaveBeenCalled();
  });
});

describe('ModalPago — cierre', () => {
  it('el botón Cancelar invoca onClose', async () => {
    const user = userEvent.setup();
    const props = renderModal();
    // Sin vuelto configurado solo existe el "Cancelar" del pie del modal.
    await user.click(screen.getByRole('button', { name: /^cancelar$/i }));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });
});
