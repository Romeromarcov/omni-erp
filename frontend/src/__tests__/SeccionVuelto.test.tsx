import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SeccionVuelto from '../components/Pedidos/SeccionVuelto';
import type { Pago, Moneda } from '../components/Pedidos/types';

const MONEDAS: Moneda[] = [
  { id_moneda: 'usd', nombre: 'Dólar', codigo_iso: 'USD', es_base: true },
  { id_moneda: 'ves', nombre: 'Bolívar', codigo_iso: 'VES', es_pais: true },
];

const VUELTO: Pago = {
  id_metodo_pago: 'efectivo',
  id_moneda: 'VES',
  monto: 73,
  tasa: 36.5,
  referencia: 'Vuelto automático',
};

function renderSeccion(overrides: Partial<React.ComponentProps<typeof SeccionVuelto>> = {}) {
  const props = {
    vueltoDisponible: 2,
    mostrarVueltos: false,
    vuelto: null,
    monedas: MONEDAS,
    monedaBase: MONEDAS[0],
    onConfigurar: vi.fn(),
    onMonedaChange: vi.fn(),
    onMontoChange: vi.fn(),
    onTasaChange: vi.fn(),
    onConfirmarVuelto: vi.fn(),
    onCancelar: vi.fn(),
    ...overrides,
  };
  render(<SeccionVuelto {...props} />);
  return props;
}

afterEach(() => cleanup());

describe('SeccionVuelto', () => {
  it('no renderiza nada cuando el vuelto disponible es 0 o negativo', () => {
    renderSeccion({ vueltoDisponible: 0 });
    expect(screen.queryByText(/vuelto disponible/i)).not.toBeInTheDocument();
    cleanup();
    renderSeccion({ vueltoDisponible: -5 });
    expect(screen.queryByText(/vuelto disponible/i)).not.toBeInTheDocument();
  });

  it('muestra el vuelto disponible en moneda base con 2 decimales', () => {
    renderSeccion({ vueltoDisponible: 2.345 });
    expect(screen.getByText(/Vuelto disponible: USD 2\.35/)).toBeInTheDocument();
  });

  it('muestra el botón "Configurar vuelto" y dispara onConfigurar', async () => {
    const user = userEvent.setup();
    const props = renderSeccion();
    await user.click(screen.getByRole('button', { name: /configurar vuelto/i }));
    expect(props.onConfigurar).toHaveBeenCalledTimes(1);
  });

  it('en modo edición permite cambiar moneda, monto y tasa convirtiendo a número', async () => {
    const user = userEvent.setup();
    const props = renderSeccion({ mostrarVueltos: true, vuelto: VUELTO });

    // Moneda (único Select de MUI en la sección; sin nombre accesible asociado)
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'USD' }));
    expect(props.onMonedaChange).toHaveBeenCalledWith('USD');

    // Monto y tasa: deben llegar como number, no como string
    fireEvent.change(screen.getByLabelText(/monto/i), { target: { value: '50.25' } });
    expect(props.onMontoChange).toHaveBeenCalledWith(50.25);

    fireEvent.change(screen.getByLabelText(/tasa/i), { target: { value: '37' } });
    expect(props.onTasaChange).toHaveBeenCalledWith(37);
  });

  it('confirma y cancela el vuelto con sus callbacks', async () => {
    const user = userEvent.setup();
    const props = renderSeccion({ mostrarVueltos: true, vuelto: VUELTO });

    await user.click(screen.getByRole('button', { name: /confirmar vuelto/i }));
    expect(props.onConfirmarVuelto).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /cancelar/i }));
    expect(props.onCancelar).toHaveBeenCalledTimes(1);
  });

  it('usa valores por defecto seguros cuando vuelto es null en modo edición', () => {
    renderSeccion({ mostrarVueltos: true, vuelto: null });
    expect(screen.getByLabelText(/monto/i)).toHaveValue(0);
    expect(screen.getByLabelText(/tasa/i)).toHaveValue(1);
  });
});
