/**
 * Tests exhaustivos de TablaProductos.
 *
 * Tabla de líneas de producto del pedido (núcleo POS). Tiene dos vistas:
 * desktop (tabla) y mobile (tarjetas), seleccionadas por useMediaQuery. Se
 * verifican cálculos con decimal.js (subtotal, monto descuento), fallbacks de
 * nombre/sku desde el catálogo, y el callback onRemove con el índice correcto.
 */
import type React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

type Mock = ReturnType<typeof vi.fn>;

// Mock controlable de useMediaQuery para forzar desktop/mobile.
const useMediaQueryMock = vi.fn();
vi.mock('@mui/material', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@mui/material')>();
  return { ...actual, useMediaQuery: () => useMediaQueryMock() };
});

import TablaProductos, { type PedidoDetalleForm } from '../TablaProductos';
import type { Producto } from '../../../services/productosService';

type CProps = React.ComponentProps<typeof TablaProductos>;

const PRODUCTOS: Producto[] = [
  { id_producto: 'p1', nombre_producto: 'Café Molido', sku: 'CAF-001', precio_venta_sugerido: 12.5 },
];

const DETALLES: PedidoDetalleForm[] = [
  // Línea con datos propios (sku/producto en el detalle)
  { id_producto: 'p1', cantidad: '2', precio_unitario: '10', descuento_porcentaje: '10', sku: 'CAF-001', producto: 'Café Molido' },
  // Línea sin sku/producto -> fallback al catálogo por id_producto
  { id_producto: 'p1', cantidad: '3', precio_unitario: '5', descuento_porcentaje: '0' },
];

function renderTabla(overrides: Partial<{
  detalles: PedidoDetalleForm[];
  productos: Producto[];
  onRemove: Mock;
}> = {}) {
  const onRemove = overrides.onRemove ?? vi.fn();
  const utils = render(
    <TablaProductos
      detalles={overrides.detalles ?? DETALLES}
      productos={overrides.productos ?? PRODUCTOS}
      onRemove={onRemove as unknown as CProps['onRemove']}
    />,
  );
  return { ...utils, onRemove };
}

describe('TablaProductos — vista desktop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMediaQueryMock.mockReturnValue(false); // isMobile=false -> desktop
  });

  it('renderiza encabezados de la tabla', () => {
    renderTabla();
    expect(screen.getByText('SKU')).toBeInTheDocument();
    expect(screen.getByText('Descripción')).toBeInTheDocument();
    expect(screen.getByText('% Desc.')).toBeInTheDocument();
    expect(screen.getByText('Monto Desc.')).toBeInTheDocument();
    expect(screen.getByText('Total')).toBeInTheDocument();
  });

  it('calcula el total de línea con descuento: 2*10 - 10% = 18.00', () => {
    renderTabla();
    const filas = screen.getAllByRole('row');
    // fila 1 = header; fila 2 = primera línea
    const fila = filas[1];
    expect(within(fila).getByText('18.00')).toBeInTheDocument();
  });

  it('calcula el monto de descuento total de la línea: 10*10%*2 = 2.00', () => {
    renderTabla({ detalles: [DETALLES[0]] });
    const fila = screen.getAllByRole('row')[1];
    // precio(10) * desc(10%) = 1.00 por unidad; * cantidad(2) = 2.00
    expect(within(fila).getByText('2.00')).toBeInTheDocument();
  });

  it('línea sin descuento: total = cantidad*precio (3*5 = 15.00)', () => {
    renderTabla({ detalles: [DETALLES[1]] });
    const fila = screen.getAllByRole('row')[1];
    expect(within(fila).getByText('15.00')).toBeInTheDocument();
  });

  it('usa fallback de sku y nombre desde el catálogo cuando el detalle no los trae', () => {
    renderTabla({ detalles: [DETALLES[1]] });
    const fila = screen.getAllByRole('row')[1];
    expect(within(fila).getByText('CAF-001')).toBeInTheDocument();
    expect(within(fila).getByText('Café Molido')).toBeInTheDocument();
  });

  it('producto desconocido (sin match en catálogo) muestra sku/nombre vacíos sin crash', () => {
    const det: PedidoDetalleForm[] = [{ id_producto: 'zzz', cantidad: '1', precio_unitario: '7' }];
    renderTabla({ detalles: det });
    const fila = screen.getAllByRole('row')[1];
    // precio y total ambos 7.00 (cantidad 1, sin descuento)
    expect(within(fila).getAllByText('7.00').length).toBeGreaterThanOrEqual(2);
  });

  it('cantidad/precio no numéricos se tratan como 0 (decimal.js D)', () => {
    const det: PedidoDetalleForm[] = [{ id_producto: 'p1', cantidad: 'abc', precio_unitario: '' }];
    renderTabla({ detalles: det });
    const fila = screen.getAllByRole('row')[1];
    // total = 0.00
    const totales = within(fila).getAllByText('0.00');
    expect(totales.length).toBeGreaterThan(0);
  });

  it('Eliminar invoca onRemove con el índice correcto', () => {
    const { onRemove } = renderTabla();
    const botones = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(botones[1]);
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('renderiza una fila por cada detalle', () => {
    renderTabla();
    // header + 2 líneas
    expect(screen.getAllByRole('row')).toHaveLength(3);
  });

  it('lista vacía no renderiza filas de datos', () => {
    renderTabla({ detalles: [] });
    // solo el header
    expect(screen.getAllByRole('row')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument();
  });
});

describe('TablaProductos — vista mobile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMediaQueryMock.mockReturnValue(true); // isMobile=true -> tarjetas
  });

  it('renderiza tarjetas con etiquetas Cantidad/Precio/Desc/Total', () => {
    renderTabla({ detalles: [DETALLES[0]] });
    expect(screen.getByText('Cantidad')).toBeInTheDocument();
    expect(screen.getByText('Precio')).toBeInTheDocument();
    expect(screen.getByText('Desc. %')).toBeInTheDocument();
    expect(screen.getByText('Total')).toBeInTheDocument();
    // No hay tabla en mobile
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('muestra el total calculado en la tarjeta (18.00)', () => {
    renderTabla({ detalles: [DETALLES[0]] });
    expect(screen.getByText('18.00')).toBeInTheDocument();
  });

  it('Eliminar en mobile invoca onRemove con el índice', () => {
    const { onRemove } = renderTabla({ detalles: DETALLES });
    const botones = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(botones[0]);
    expect(onRemove).toHaveBeenCalledWith(0);
  });

  it('usa fallback de catálogo en la tarjeta cuando faltan sku/nombre', () => {
    renderTabla({ detalles: [DETALLES[1]] });
    expect(screen.getByText('CAF-001')).toBeInTheDocument();
    expect(screen.getByText('Café Molido')).toBeInTheDocument();
  });
});
