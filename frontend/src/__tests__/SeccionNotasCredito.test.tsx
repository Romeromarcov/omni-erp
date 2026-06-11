import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SeccionNotasCredito from '../components/Pedidos/SeccionNotasCredito';
import type { NotaCredito, Moneda } from '../components/Pedidos/types';

const USD: Moneda = { id_moneda: 'usd', nombre: 'Dólar', codigo_iso: 'USD', es_base: true };
const VES: Moneda = { id_moneda: 'ves', nombre: 'Bolívar', codigo_iso: 'VES', es_pais: true };

const NC_USD: NotaCredito = {
  id_nota_credito: 'nc-usd',
  numero_nota: 'NC-001',
  monto_disponible: 10,
  id_moneda: 'usd',
  fecha_emision: '2026-01-15T00:00:00Z',
};

const NC_VES: NotaCredito = {
  id_nota_credito: 'nc-ves',
  numero_nota: 'NC-002',
  monto_disponible: 365,
  id_moneda: 'ves',
  fecha_emision: '2026-02-01T00:00:00Z',
  fecha_vencimiento: '2026-12-31T00:00:00Z',
};

function renderSeccion(overrides: Partial<React.ComponentProps<typeof SeccionNotasCredito>> = {}) {
  const props: React.ComponentProps<typeof SeccionNotasCredito> = {
    notasCredito: [NC_USD, NC_VES],
    notasCreditoSeleccionadas: [],
    monedas: [USD, VES],
    monedaBase: USD,
    monedaPais: VES,
    tasaBCV: 36.5,
    onToggle: vi.fn(),
    ...overrides,
  };
  render(<SeccionNotasCredito {...props} />);
  return props;
}

afterEach(() => cleanup());

describe('SeccionNotasCredito', () => {
  it('no renderiza nada si no hay notas de crédito disponibles', () => {
    renderSeccion({ notasCredito: [] });
    expect(screen.queryByText(/notas de crédito disponibles/i)).not.toBeInTheDocument();
  });

  it('lista cada nota con su número, moneda y monto disponible', () => {
    renderSeccion();
    expect(screen.getByText(/NC-001 — USD 10\.00/)).toBeInTheDocument();
    expect(screen.getByText(/NC-002 — VES 365\.00/)).toBeInTheDocument();
  });

  it('dispara onToggle con la nota al pulsar Aplicar', async () => {
    const user = userEvent.setup();
    const props = renderSeccion();
    const botones = screen.getAllByRole('button', { name: /aplicar/i });
    await user.click(botones[0]);
    expect(props.onToggle).toHaveBeenCalledWith(NC_USD);
  });

  it('muestra "Quitar" para la nota seleccionada y permite deseleccionarla', async () => {
    const user = userEvent.setup();
    const props = renderSeccion({ notasCreditoSeleccionadas: [NC_USD] });
    const quitar = screen.getByRole('button', { name: /quitar/i });
    await user.click(quitar);
    expect(props.onToggle).toHaveBeenCalledWith(NC_USD);
  });

  it('convierte a moneda base el total aplicado: NC en base cuenta 1:1', () => {
    renderSeccion({ notasCreditoSeleccionadas: [NC_USD] });
    expect(screen.getByText(/Total aplicado: USD 10\.00/)).toBeInTheDocument();
  });

  it('convierte a moneda base el total aplicado: NC en moneda país divide por la tasa BCV', () => {
    // 365 VES / 36.5 = 10 USD
    renderSeccion({ notasCreditoSeleccionadas: [NC_VES] });
    expect(screen.getByText(/Total aplicado: USD 10\.00/)).toBeInTheDocument();
  });

  it('suma ambas notas convertidas cuando hay varias seleccionadas', () => {
    renderSeccion({ notasCreditoSeleccionadas: [NC_USD, NC_VES] });
    expect(screen.getByText(/Total aplicado: USD 20\.00/)).toBeInTheDocument();
  });

  it('no muestra total aplicado sin selección', () => {
    renderSeccion();
    expect(screen.queryByText(/total aplicado/i)).not.toBeInTheDocument();
  });
});
