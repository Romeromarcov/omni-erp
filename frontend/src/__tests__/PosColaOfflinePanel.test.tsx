import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import PosColaOfflinePanel from '../pages/Ventas/POS/PosColaOfflinePanel';
import type { OutboxSale } from '../lib/salesOutbox';

const ITEMS: OutboxSale[] = [
  {
    idempotencyKey: 'uuid-pend-1234',
    endpoint: '/sync/push/ventas/',
    payload: { fecha_local: '2026-11-19T10:00:00.000Z', totales_cliente: { total: '12.50' } },
    createdAt: 1_700_000_000_000,
    estado: 'PENDIENTE',
    folioProvisional: 'POS-pend-123',
    totalProvisional: '12.50',
    codigoIso: 'VES',
  },
  {
    idempotencyKey: 'uuid-rev-5678',
    endpoint: '/sync/push/ventas/',
    payload: { totales_cliente: { total: '20.00' } },
    createdAt: 1_700_000_001_000,
    estado: 'REQUIERE_REVISION',
    folioProvisional: 'POS-rev-567',
    totalProvisional: '20.00',
    codigoIso: 'VES',
    errorMensaje: 'Stock insuficiente en almacén principal.',
    errorCodigo: 'REQUIERE_REVISION',
    errorStatus: 422,
  },
  {
    idempotencyKey: 'uuid-sync-9012',
    endpoint: '/sync/push/ventas/',
    payload: {},
    createdAt: 1_700_000_002_000,
    estado: 'SINCRONIZADA',
    folioProvisional: 'POS-sync-90',
    totalProvisional: '8.00',
    codigoIso: 'VES',
    idNotaVenta: 'nv-srv-99',
    numeroNota: 'POS-00099',
    alertaStockNegativo: true,
    syncedAt: 1_700_000_005_000,
  },
];

describe('PosColaOfflinePanel', () => {
  it('muestra estado vacío cuando no hay ventas en cola', () => {
    render(
      <PosColaOfflinePanel
        open
        items={[]}
        online
        flushing={false}
        onClose={vi.fn()}
        onSincronizarAhora={vi.fn()}
        onReintentar={vi.fn()}
        onDescartar={vi.fn()}
        onLimpiarSincronizadas={vi.fn()}
      />,
    );
    expect(screen.getByTestId('pos-cola-vacia')).toBeInTheDocument();
    expect(screen.getByTestId('pos-cola-sincronizar')).toBeDisabled();
  });

  it('muestra pendientes, en revisión y sincronizadas con acciones funcionales', () => {
    const onSincronizarAhora = vi.fn();
    const onReintentar = vi.fn();
    const onDescartar = vi.fn();
    const onLimpiarSincronizadas = vi.fn();
    const onClose = vi.fn();

    render(
      <PosColaOfflinePanel
        open
        items={ITEMS}
        online
        flushing={false}
        onClose={onClose}
        onSincronizarAhora={onSincronizarAhora}
        onReintentar={onReintentar}
        onDescartar={onDescartar}
        onLimpiarSincronizadas={onLimpiarSincronizadas}
      />,
    );

    expect(screen.getByTestId('pos-cola-pendiente-uuid-pend-1234').textContent).toContain('POS-pend-123');
    expect(screen.getByTestId('pos-cola-revision-uuid-rev-5678').textContent).toContain(
      'Stock insuficiente en almacén principal.',
    );
    expect(screen.getByTestId('pos-cola-revision-uuid-rev-5678').textContent).toContain('REQUIERE_REVISION');
    expect(screen.getByTestId('pos-cola-sincronizada-uuid-sync-9012').textContent).toContain(
      'POS-sync-90 → POS-00099',
    );
    expect(screen.getByTestId('pos-cola-sincronizada-uuid-sync-9012').textContent).toContain('Stock negativo');

    fireEvent.click(screen.getByTestId('pos-cola-sincronizar'));
    expect(onSincronizarAhora).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('pos-cola-reintentar-uuid-rev-5678'));
    expect(onReintentar).toHaveBeenCalledWith('uuid-rev-5678');

    fireEvent.click(screen.getByTestId('pos-cola-descartar-uuid-rev-5678'));
    expect(onDescartar).toHaveBeenCalledWith('uuid-rev-5678');

    fireEvent.click(screen.getByTestId('pos-cola-limpiar-historial'));
    expect(onLimpiarSincronizadas).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('pos-cola-cerrar'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('deshabilita sincronización manual cuando está offline', () => {
    render(
      <PosColaOfflinePanel
        open
        items={[ITEMS[0]]}
        online={false}
        flushing={false}
        onClose={vi.fn()}
        onSincronizarAhora={vi.fn()}
        onReintentar={vi.fn()}
        onDescartar={vi.fn()}
        onLimpiarSincronizadas={vi.fn()}
      />,
    );
    expect(screen.getByTestId('pos-cola-estado-red').textContent).toContain('Sin conexión');
    expect(screen.getByTestId('pos-cola-sincronizar')).toBeDisabled();
  });

  it('deshabilita Reintentar, Descartar y Limpiar historial mientras flushing está en curso', () => {
    render(
      <PosColaOfflinePanel
        open
        items={ITEMS}
        online
        flushing
        onClose={vi.fn()}
        onSincronizarAhora={vi.fn()}
        onReintentar={vi.fn()}
        onDescartar={vi.fn()}
        onLimpiarSincronizadas={vi.fn()}
      />,
    );
    expect(screen.getByTestId('pos-cola-sincronizar')).toBeDisabled();
    expect(screen.getByTestId('pos-cola-reintentar-uuid-rev-5678')).toBeDisabled();
    expect(screen.getByTestId('pos-cola-descartar-uuid-rev-5678')).toBeDisabled();
    expect(screen.getByTestId('pos-cola-limpiar-historial')).toBeDisabled();
  });
});
