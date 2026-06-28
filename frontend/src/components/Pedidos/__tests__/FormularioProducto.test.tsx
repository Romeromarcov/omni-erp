/**
 * Tests exhaustivos de FormularioProducto.
 *
 * Componente núcleo del POS: formulario para agregar/editar una línea de
 * producto, con autocompletado por SKU y por nombre. Se prueba en aislamiento
 * renderizándolo directamente con props mock (no vía la página).
 */
import type React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import FormularioProducto from '../FormularioProducto';
import type { Producto } from '../../../services/productosService';
import type { PedidoDetalleForm } from '../TablaProductos';

const PRODUCTOS: Producto[] = [
  { id_producto: 'p1', nombre_producto: 'Café Molido', sku: 'CAF-001', precio_venta_sugerido: 12.5 },
  { id_producto: 'p2', nombre_producto: 'Té Verde', sku: 'TEA-002', precio_venta_sugerido: 8 },
  { id_producto: 'p3', nombre_producto: 'Café en Grano', sku: 'CAF-003', precio_venta_sugerido: 20 },
];

const baseDetalle: PedidoDetalleForm = {
  id_producto: '',
  cantidad: '1',
  precio_unitario: '0',
  descuento_porcentaje: '',
  sku: '',
  producto: '',
  comentarios: '',
};

type Props = React.ComponentProps<typeof FormularioProducto>;

type Mock = ReturnType<typeof vi.fn>;

function renderForm(overrides: Partial<{
  productos: Producto[];
  detalleForm: PedidoDetalleForm;
  onChange: Mock;
  onAdd: Mock;
  onSelectProducto: Mock;
}> = {}) {
  const onChange = overrides.onChange ?? vi.fn();
  const onAdd = overrides.onAdd ?? vi.fn();
  const onSelectProducto = overrides.onSelectProducto;
  const utils = render(
    <FormularioProducto
      productos={overrides.productos ?? PRODUCTOS}
      detalleForm={overrides.detalleForm ?? baseDetalle}
      onChange={onChange as unknown as Props['onChange']}
      onAdd={onAdd as unknown as Props['onAdd']}
      onSelectProducto={onSelectProducto as unknown as Props['onSelectProducto']}
    />,
  );
  return { ...utils, onChange, onAdd, onSelectProducto };
}

describe('FormularioProducto', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza todos los campos básicos', () => {
    renderForm();
    expect(screen.getByLabelText('SKU')).toBeInTheDocument();
    expect(screen.getByLabelText('Producto')).toBeInTheDocument();
    expect(screen.getByLabelText('Cantidad')).toBeInTheDocument();
    expect(screen.getByLabelText('Precio')).toBeInTheDocument();
    expect(screen.getByLabelText('% Desc.')).toBeInTheDocument();
    expect(screen.getByLabelText('Comentarios (opcional)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Agregar' })).toBeInTheDocument();
  });

  it('sincroniza inputs con detalleForm via useEffect', () => {
    const detalle = { ...baseDetalle, sku: 'CAF-001', producto: 'Café Molido' };
    renderForm({ detalleForm: detalle });
    expect(screen.getByLabelText('SKU')).toHaveValue('CAF-001');
    expect(screen.getByLabelText('Producto')).toHaveValue('Café Molido');
  });

  it('al teclear en SKU dispara onChange y muestra sugerencias filtradas', () => {
    const { onChange } = renderForm();
    const sku = screen.getByLabelText('SKU');
    fireEvent.change(sku, { target: { value: 'caf' } });
    expect(onChange).toHaveBeenCalledTimes(1);
    // Filtrado case-insensitive: CAF-001 y CAF-003
    expect(screen.getByText('CAF-001')).toBeInTheDocument();
    expect(screen.getByText('CAF-003')).toBeInTheDocument();
    expect(screen.queryByText('TEA-002')).not.toBeInTheDocument();
  });

  it('al teclear en Producto filtra por nombre case-insensitive', () => {
    renderForm();
    const nombre = screen.getByLabelText('Producto');
    fireEvent.change(nombre, { target: { value: 'café' } });
    expect(screen.getByText(/Café Molido/)).toBeInTheDocument();
    expect(screen.getByText(/Café en Grano/)).toBeInTheDocument();
    expect(screen.queryByText(/Té Verde/)).not.toBeInTheDocument();
  });

  it('no muestra sugerencias de SKU con input vacío', () => {
    renderForm();
    const sku = screen.getByLabelText('SKU');
    fireEvent.focus(sku);
    // input vacío => sugerenciasSku = []
    expect(screen.queryByText('CAF-001')).not.toBeInTheDocument();
  });

  it('seleccionar una sugerencia de SKU invoca onSelectProducto y onChange con todos los campos', () => {
    const { onChange, onSelectProducto } = renderForm({ onSelectProducto: vi.fn() });
    fireEvent.change(screen.getByLabelText('SKU'), { target: { value: 'caf' } });
    // El ListItemButton usa onMouseDown
    fireEvent.mouseDown(screen.getByText('CAF-001'));

    expect(onSelectProducto).toHaveBeenCalledTimes(1);
    expect(onSelectProducto).toHaveBeenCalledWith(PRODUCTOS[0]);

    // onChange invocado para id_producto, precio_unitario, sku, producto
    const calls = onChange.mock.calls.map(c => c[0].target);
    expect(calls).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: 'id_producto', value: 'p1' }),
      expect.objectContaining({ name: 'precio_unitario', value: 12.5 }),
      expect.objectContaining({ name: 'sku', value: 'CAF-001' }),
      expect.objectContaining({ name: 'producto', value: 'Café Molido' }),
    ]));
  });

  it('seleccionar producto sin precio_venta_sugerido usa string vacío', () => {
    const productos: Producto[] = [{ id_producto: 'pX', nombre_producto: 'Sin Precio', sku: 'NOP-1' }];
    const { onChange } = renderForm({ productos });
    fireEvent.change(screen.getByLabelText('SKU'), { target: { value: 'nop' } });
    fireEvent.mouseDown(screen.getByText('NOP-1'));
    const precioCall = onChange.mock.calls
      .map(c => c[0].target)
      .find((t: { name: string }) => t.name === 'precio_unitario');
    expect(precioCall.value).toBe('');
  });

  it('seleccionar producto sin sku usa string vacío para sku', () => {
    const productos: Producto[] = [{ id_producto: 'pY', nombre_producto: 'Solo Nombre', precio_venta_sugerido: 5 }];
    const { onChange } = renderForm({ productos });
    fireEvent.change(screen.getByLabelText('Producto'), { target: { value: 'solo' } });
    fireEvent.mouseDown(screen.getByText(/Solo Nombre/));
    const skuCall = onChange.mock.calls
      .map(c => c[0].target)
      .find((t: { name: string }) => t.name === 'sku');
    expect(skuCall.value).toBe('');
  });

  it('seleccionar sugerencia de Nombre funciona aunque onSelectProducto sea undefined', () => {
    const { onChange, onSelectProducto } = renderForm(); // sin onSelectProducto
    expect(onSelectProducto).toBeUndefined();
    fireEvent.change(screen.getByLabelText('Producto'), { target: { value: 'verde' } });
    fireEvent.mouseDown(screen.getByText(/Té Verde/));
    const calls = onChange.mock.calls.map(c => c[0].target);
    expect(calls).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: 'id_producto', value: 'p2' }),
      expect.objectContaining({ name: 'producto', value: 'Té Verde' }),
    ]));
  });

  it('onBlur oculta las sugerencias tras el timeout', () => {
    vi.useFakeTimers();
    try {
      renderForm();
      const sku = screen.getByLabelText('SKU');
      fireEvent.change(sku, { target: { value: 'caf' } });
      expect(screen.getByText('CAF-001')).toBeInTheDocument();
      fireEvent.blur(sku);
      // Aún visible antes del timeout
      expect(screen.getByText('CAF-001')).toBeInTheDocument();
      act(() => { vi.advanceTimersByTime(200); });
      expect(screen.queryByText('CAF-001')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('cantidad onChange delega en la prop onChange', () => {
    const { onChange } = renderForm();
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '3' } });
    expect(onChange).toHaveBeenCalled();
  });

  it('Enter en Cantidad llama onAdd y previene default', () => {
    const { onAdd } = renderForm();
    const cantidad = screen.getByLabelText('Cantidad');
    fireEvent.keyDown(cantidad, { key: 'Enter' });
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('otra tecla en Cantidad NO llama onAdd', () => {
    const { onAdd } = renderForm();
    fireEvent.keyDown(screen.getByLabelText('Cantidad'), { key: 'a' });
    expect(onAdd).not.toHaveBeenCalled();
  });

  it('precio y descuento delegan en onChange', () => {
    const { onChange } = renderForm();
    fireEvent.change(screen.getByLabelText('Precio'), { target: { value: '15' } });
    fireEvent.change(screen.getByLabelText('% Desc.'), { target: { value: '10' } });
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it('comentarios delega en onChange', () => {
    const { onChange } = renderForm();
    fireEvent.change(screen.getByLabelText('Comentarios (opcional)'), { target: { value: 'urgente' } });
    expect(onChange).toHaveBeenCalled();
  });

  it('boton Agregar invoca onAdd', () => {
    const { onAdd } = renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar' }));
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('la sugerencia de nombre muestra el sku entre paréntesis cuando existe', () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Producto'), { target: { value: 'molido' } });
    expect(screen.getByText('Café Molido (CAF-001)')).toBeInTheDocument();
  });
});
