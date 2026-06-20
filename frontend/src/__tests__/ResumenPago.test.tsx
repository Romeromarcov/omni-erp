import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import ResumenPago from '../components/Pedidos/ResumenPago';
import type { Moneda } from '../components/Pedidos/types';

const USD: Moneda = { id_moneda: 'usd', nombre: 'Dólar', codigo_iso: 'USD', es_base: true };
const VES: Moneda = { id_moneda: 'ves', nombre: 'Bolívar', codigo_iso: 'VES', es_pais: true };

// Misma regla que ModalPago: diferencia positiva dentro de tolerancia,
// negativa solo si se permite.
const aceptable = (tolerancia: number, permitirNegativas: boolean) => (d: number) =>
  d > 0 ? d <= tolerancia : permitirNegativas;

function renderResumen(overrides: Partial<React.ComponentProps<typeof ResumenPago>> = {}) {
  const props: React.ComponentProps<typeof ResumenPago> = {
    monto: 100,
    totalPagadoConNotasBase: 100,
    saldoRestante: 0,
    toleranciaPositiva: 0.5,
    notasCreditoCount: 0,
    monedaBase: USD,
    monedaPais: VES,
    tasaBCV: 36.5,
    esDiferenciaAceptable: aceptable(0.5, true),
    ...overrides,
  };
  render(<ResumenPago {...props} />);
  return props;
}

afterEach(() => cleanup());

describe('ResumenPago', () => {
  it('muestra el total del documento en base y su conversión a moneda país por la tasa BCV', () => {
    renderResumen({ monto: 100, totalPagadoConNotasBase: 0, saldoRestante: 100, tasaBCV: 36.5 });
    expect(screen.getAllByText('USD 100.00')).toHaveLength(2); // documento y diferencia
    expect(screen.getAllByText('VES 3650.00')).toHaveLength(2);
    expect(screen.getByText('USD 0.00')).toBeInTheDocument(); // total pagado
  });

  it('muestra el total pagado y la diferencia con sus conversiones', () => {
    renderResumen({ monto: 100, totalPagadoConNotasBase: 60, saldoRestante: 40, tasaBCV: 10 });
    expect(screen.getByText('USD 60.00')).toBeInTheDocument();
    expect(screen.getByText('VES 600.00')).toBeInTheDocument();
    expect(screen.getByText('USD 40.00')).toBeInTheDocument();
    expect(screen.getByText('VES 400.00')).toBeInTheDocument();
  });

  it('indica que el saldo está dentro de tolerancia cuando 0 <= saldo <= tolerancia', () => {
    renderResumen({ saldoRestante: 0.5, toleranciaPositiva: 0.5 });
    expect(screen.getByText(/dentro de tolerancia positiva/i)).toBeInTheDocument();
    expect(screen.queryByText(/diferencia positiva excesiva/i)).not.toBeInTheDocument();
  });

  it('marca la diferencia positiva excesiva cuando supera la tolerancia', () => {
    renderResumen({ saldoRestante: 1.2, toleranciaPositiva: 0.5 });
    expect(screen.getByText(/diferencia positiva excesiva \(> 0\.50\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/dentro de tolerancia/i)).not.toBeInTheDocument();
  });

  it('marca la diferencia negativa como aceptable cuando se permiten negativas', () => {
    renderResumen({ saldoRestante: -3, esDiferenciaAceptable: aceptable(0.5, true) });
    expect(screen.getByText(/diferencia negativa aceptable/i)).toBeInTheDocument();
  });

  it('NO marca la diferencia negativa como aceptable cuando no se permiten negativas', () => {
    renderResumen({ saldoRestante: -3, esDiferenciaAceptable: aceptable(0.5, false) });
    expect(screen.queryByText(/diferencia negativa aceptable/i)).not.toBeInTheDocument();
  });

  it('convierte a moneda país con precisión decimal (BUG-M6 / FE-HIGH-7)', () => {
    // Con float, 0.1 * 1.15 = 0.11499999… → toFixed(2) = "0.11" (incorrecto).
    // Con decimal.js, 0.1 * 1.15 = 0.115 → redondeo half-up = "0.12".
    renderResumen({ monto: 0.1, totalPagadoConNotasBase: 0, saldoRestante: 0.1, tasaBCV: 1.15 });
    expect(screen.getAllByText('VES 0.12')).toHaveLength(2); // documento y diferencia
    expect(screen.queryByText('VES 0.11')).not.toBeInTheDocument();
  });

  it('refleja el conteo de notas de crédito en el rótulo de pagos', () => {
    renderResumen({ notasCreditoCount: 2 });
    expect(screen.getByText(/total pagos \+ 2 nc/i)).toBeInTheDocument();
  });
});
