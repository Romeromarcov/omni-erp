/**
 * Tests exhaustivos de ModalBusquedaProducto.
 *
 * Modal de búsqueda de producto del POS. Filtra por nombre (case-insensitive),
 * selecciona vía botón o tecla Enter (primer resultado) y delega en onSelect/onClose.
 */
import type React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ModalBusquedaProducto from '../ModalBusquedaProducto';
import type { Producto } from '../../../services/productosService';

type Mock = ReturnType<typeof vi.fn>;
type CProps = React.ComponentProps<typeof ModalBusquedaProducto>;

const PRODUCTOS: Producto[] = [
  { id_producto: 'p1', nombre_producto: 'Café Molido', sku: 'CAF-001', precio_venta_sugerido: 12.5 },
  { id_producto: 'p2', nombre_producto: 'Té Verde', sku: 'TEA-002', precio_venta_sugerido: 8 },
  { id_producto: 'p3', nombre_producto: 'Café en Grano', sku: 'CAF-003' }, // sin precio
];

function renderModal(overrides: Partial<{
  open: boolean;
  productos: Producto[];
  onSelect: Mock;
  onClose: Mock;
}> = {}) {
  const onSelect = overrides.onSelect ?? vi.fn();
  const onClose = overrides.onClose ?? vi.fn();
  const utils = render(
    <ModalBusquedaProducto
      open={overrides.open ?? true}
      productos={overrides.productos ?? PRODUCTOS}
      onSelect={onSelect as unknown as CProps['onSelect']}
      onClose={onClose as unknown as CProps['onClose']}
    />,
  );
  return { ...utils, onSelect, onClose };
}

describe('ModalBusquedaProducto', () => {
  beforeEach(() => vi.clearAllMocks());

  it('no renderiza contenido cuando open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByText('Buscar producto')).not.toBeInTheDocument();
  });

  it('renderiza título y todos los productos por defecto (sin búsqueda)', () => {
    renderModal();
    expect(screen.getByText('Buscar producto')).toBeInTheDocument();
    expect(screen.getByText('Café Molido')).toBeInTheDocument();
    expect(screen.getByText('Té Verde')).toBeInTheDocument();
    expect(screen.getByText('Café en Grano')).toBeInTheDocument();
  });

  it('muestra el precio formateado a 2 decimales y N/A cuando no hay precio', () => {
    renderModal();
    expect(screen.getByText(/SKU: CAF-001 \| Precio: 12\.50/)).toBeInTheDocument();
    expect(screen.getByText(/SKU: CAF-003 \| Precio: N\/A/)).toBeInTheDocument();
  });

  it('filtra por nombre case-insensitive al teclear', () => {
    renderModal();
    const input = screen.getByPlaceholderText('Buscar por nombre...');
    fireEvent.change(input, { target: { value: 'café' } });
    expect(screen.getByText('Café Molido')).toBeInTheDocument();
    expect(screen.getByText('Café en Grano')).toBeInTheDocument();
    expect(screen.queryByText('Té Verde')).not.toBeInTheDocument();
  });

  it('muestra el texto vacío cuando no hay coincidencias', () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre...'), { target: { value: 'zzz' } });
    expect(screen.getByText('No se encontraron productos.')).toBeInTheDocument();
  });

  it('el botón Seleccionar invoca onSelect con el producto y cierra', () => {
    const { onSelect, onClose } = renderModal();
    const botones = screen.getAllByRole('button', { name: 'Seleccionar' });
    fireEvent.click(botones[0]);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(PRODUCTOS[0]);
    expect(onClose).toHaveBeenCalled();
  });

  it('Enter selecciona el primer resultado filtrado y cierra', () => {
    const { onSelect, onClose } = renderModal();
    const input = screen.getByPlaceholderText('Buscar por nombre...');
    fireEvent.change(input, { target: { value: 'grano' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(PRODUCTOS[2]); // Café en Grano
    expect(onClose).toHaveBeenCalled();
  });

  it('Enter sin resultados NO invoca onSelect', () => {
    const { onSelect } = renderModal();
    const input = screen.getByPlaceholderText('Buscar por nombre...');
    fireEvent.change(input, { target: { value: 'zzz' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('el botón Cerrar invoca onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
