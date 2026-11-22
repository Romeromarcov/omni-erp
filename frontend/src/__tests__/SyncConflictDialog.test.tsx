import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SyncConflictDialog from '../components/sync/SyncConflictDialog';
import type { SyncConflictItem } from '../lib/syncConflictQueue';

const sampleConflict: SyncConflictItem = {
  conflictKey: 'clientes:cli-123',
  mutation: {
    entity: 'clientes',
    id: 'cli-123',
    expected_fecha_actualizacion: '2026-11-22T10:00:00Z',
    cambios: {
      telefono: '0414-LOCAL',
      activo: false,
    },
  },
  serverRecord: {
    id_cliente: 'cli-123',
    telefono: '0424-SERVIDOR',
    activo: true,
    fecha_actualizacion: '2026-11-22T11:45:00Z',
  },
  message: 'El registro fue modificado en el servidor.',
  detectedAt: '2026-11-22T11:46:00Z',
};

describe('SyncConflictDialog', () => {
  it('muestra la comparación local vs servidor y dispara reintento y descarte', () => {
    const onRetry = vi.fn();
    const onDiscard = vi.fn();
    const onClose = vi.fn();

    render(
      <SyncConflictDialog
        open
        conflicts={[sampleConflict]}
        onClose={onClose}
        onRetryWithServerCursor={onRetry}
        onAcceptServerVersion={onDiscard}
      />,
    );

    expect(screen.getByTestId('sync-conflict-item-clientes:cli-123')).toBeInTheDocument();
    expect(screen.getByTestId('conflict-local-telefono')).toHaveTextContent('0414-LOCAL');
    expect(screen.getByTestId('conflict-server-telefono')).toHaveTextContent('0424-SERVIDOR');
    expect(screen.getByTestId('conflict-local-activo')).toHaveTextContent('No');
    expect(screen.getByTestId('conflict-server-activo')).toHaveTextContent('Sí');

    fireEvent.click(screen.getByTestId('sync-conflict-retry-clientes:cli-123'));
    expect(onRetry).toHaveBeenCalledWith(sampleConflict);

    fireEvent.click(screen.getByTestId('sync-conflict-discard-clientes:cli-123'));
    expect(onDiscard).toHaveBeenCalledWith('clientes:cli-123');

    fireEvent.click(screen.getByTestId('sync-conflict-close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('muestra estado vacío y mensaje de error cuando corresponde', () => {
    render(
      <SyncConflictDialog
        open
        conflicts={[]}
        errorMessage="Error de red temporal"
        onClose={() => undefined}
        onRetryWithServerCursor={() => undefined}
        onAcceptServerVersion={() => undefined}
      />,
    );

    expect(screen.getByTestId('sync-conflict-error')).toHaveTextContent('Error de red temporal');
    expect(screen.getByTestId('sync-conflict-empty')).toBeInTheDocument();
  });
});
