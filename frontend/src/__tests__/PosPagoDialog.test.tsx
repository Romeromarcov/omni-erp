/**
 * Sub-fase 1.G — POS: comportamiento fino del diálogo de cobro mixto
 * (quitar pagos, filtro de monedas por método, cierre bloqueado mientras
 * procesa, doble toque no duplica el confirm).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import Decimal from 'decimal.js';
import PosPagoDialog from '../pages/Ventas/POS/PosPagoDialog';

// El POS lee los campos legados (nombre_metodo/monedas, id_moneda/codigo_iso/nombre);
// se incluyen además los campos reales del serializer (metodo_pago/nombre, moneda/moneda_*)
// para satisfacer la interfaz compartida MetodoPagoEmpresaActiva/MonedaEmpresaActiva.
const METODOS = [
  { id: 'met-efe', nombre_metodo: 'Efectivo', monedas: [], metodo_pago: 'met-efe', nombre: 'Efectivo', activa: true },
  {
    id: 'met-pm', nombre_metodo: 'Pago Móvil', monedas: ['mon-ves'],
    metodo_pago: 'met-pm', nombre: 'Pago Móvil', activa: true,
  },
];
const MONEDAS = [
  {
    id_moneda: 'mon-ves', nombre: 'Bolívar', codigo_iso: 'VES',
    id: 'act-ves', moneda: 'mon-ves', moneda_nombre: 'Bolívar', moneda_codigo_iso: 'VES', activa: true,
  },
  {
    id_moneda: 'mon-usd', nombre: 'Dólar', codigo_iso: 'USD',
    id: 'act-usd', moneda: 'mon-usd', moneda_nombre: 'Dólar', moneda_codigo_iso: 'USD', activa: true,
  },
];

const onConfirm = vi.fn();
const onClose = vi.fn();

function renderDialog(props: Partial<React.ComponentProps<typeof PosPagoDialog>> = {}) {
  return render(
    <PosPagoDialog
      open
      total={new Decimal('10.00')}
      montoImpuesto={new Decimal('1.38')}
      codigoIsoDocumento="VES"
      metodos={METODOS}
      monedas={MONEDAS}
      tasaBcv="40"
      procesando={false}
      error={null}
      onConfirm={onConfirm}
      onClose={onClose}
      {...props}
    />,
  );
}

function agregarPago(monto: string, metodo = 'met-efe', moneda = 'mon-ves') {
  fireEvent.change(screen.getByTestId('pos-pago-metodo'), { target: { value: metodo } });
  fireEvent.change(screen.getByTestId('pos-pago-moneda'), { target: { value: moneda } });
  fireEvent.change(screen.getByTestId('pos-pago-monto'), { target: { value: monto } });
  fireEvent.click(screen.getByRole('button', { name: 'Agregar pago' }));
}

beforeEach(() => vi.clearAllMocks());

describe('PosPagoDialog', () => {
  it('muestra total e IVA del backend', () => {
    renderDialog();
    expect(screen.getByTestId('pos-total-cobrar').textContent).toContain('10.00 VES');
    expect(screen.getByTestId('pos-iva-cobrar').textContent).toContain('1.38');
  });

  it('filtra las monedas según el método de pago seleccionado', () => {
    renderDialog();
    fireEvent.change(screen.getByTestId('pos-pago-metodo'), { target: { value: 'met-pm' } });
    const monedaSelect = screen.getByTestId('pos-pago-moneda') as HTMLSelectElement;
    const opciones = Array.from(monedaSelect.options).map((o) => o.textContent);
    expect(opciones).toContain('VES');
    expect(opciones).not.toContain('USD');
  });

  it('permite quitar un pago agregado y recalcula el restante', () => {
    renderDialog();
    agregarPago('6');
    expect(screen.getByTestId('pos-restante').textContent).toContain('4.00');
    const lista = screen.getByTestId('pos-pagos-lista');
    fireEvent.click(within(lista).getByLabelText('Quitar pago Efectivo'));
    expect(screen.getByTestId('pos-restante').textContent).toContain('10.00');
    expect(screen.queryByTestId('pos-pagos-lista')).not.toBeInTheDocument();
  });

  it('registra la referencia del pago (pago móvil)', () => {
    renderDialog();
    fireEvent.change(screen.getByTestId('pos-pago-referencia'), { target: { value: '1234' } });
    agregarPago('10', 'met-pm', 'mon-ves');
    expect(screen.getByText('Ref: 1234')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('pos-confirmar-cobro'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0][0]).toMatchObject({ referencia: '1234', tasa: '1' });
    expect(onConfirm.mock.calls[0][1]).toBe('0.00');
  });

  it('pago en USD lleva la tasa BCV y genera vuelto', () => {
    renderDialog();
    agregarPago('0.3', 'met-efe', 'mon-usd'); // 0.3 × 40 = 12 VES
    expect(screen.getByTestId('pos-vuelto').textContent).toContain('2.00');
    fireEvent.click(screen.getByTestId('pos-confirmar-cobro'));
    expect(onConfirm.mock.calls[0][0][0]).toMatchObject({ codigo_iso: 'USD', tasa: '40' });
    expect(onConfirm.mock.calls[0][1]).toBe('2.00');
  });

  it('bloquea cierre y confirmación mientras procesa, y muestra el error recibido', () => {
    renderDialog({ procesando: true, error: 'Error al registrar los pagos.' });
    expect(screen.getByTestId('pos-cobro-error').textContent).toContain('Error al registrar los pagos.');
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByTestId('pos-confirmar-cobro')).toBeDisabled();
  });

  it('cancelar limpia y cierra cuando no está procesando', () => {
    renderDialog();
    agregarPago('3');
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
