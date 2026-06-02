import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import { FeedbackProvider } from '../contexts/FeedbackContext';
import { useConfirm, useSnackbar } from '../contexts/feedbackTypes';

afterEach(cleanup);

function SnackbarHarness() {
  const snackbar = useSnackbar();
  return (
    <div>
      <button onClick={() => snackbar.success('Operación exitosa')}>ok</button>
      <button onClick={() => snackbar.error('Algo falló')}>err</button>
    </div>
  );
}

function ConfirmHarness({ onResult }: { onResult: (v: boolean) => void }) {
  const confirm = useConfirm();
  return (
    <button
      onClick={async () => {
        const res = await confirm({
          message: '¿Eliminar?',
          confirmText: 'Eliminar',
          destructive: true,
        });
        onResult(res);
      }}
    >
      borrar
    </button>
  );
}

describe('FeedbackContext', () => {
  it('useSnackbar muestra el mensaje en un Alert', async () => {
    render(
      <FeedbackProvider>
        <SnackbarHarness />
      </FeedbackProvider>,
    );
    fireEvent.click(screen.getByText('ok'));
    expect(await screen.findByText('Operación exitosa')).toBeInTheDocument();
  });

  it('useConfirm resuelve true al confirmar', async () => {
    let result: boolean | null = null;
    render(
      <FeedbackProvider>
        <ConfirmHarness onResult={(v) => (result = v)} />
      </FeedbackProvider>,
    );
    fireEvent.click(screen.getByText('borrar'));
    const confirmBtn = await screen.findByRole('button', { name: 'Eliminar' });
    await act(async () => {
      fireEvent.click(confirmBtn);
    });
    await waitFor(() => expect(result).toBe(true));
  });

  it('useConfirm resuelve false al cancelar', async () => {
    let result: boolean | null = null;
    render(
      <FeedbackProvider>
        <ConfirmHarness onResult={(v) => (result = v)} />
      </FeedbackProvider>,
    );
    fireEvent.click(screen.getByText('borrar'));
    const cancelBtn = await screen.findByRole('button', { name: 'Cancelar' });
    await act(async () => {
      fireEvent.click(cancelBtn);
    });
    await waitFor(() => expect(result).toBe(false));
  });

  it('los hooks lanzan si no hay provider', () => {
    function Bare() {
      useSnackbar();
      return null;
    }
    expect(() => render(<Bare />)).toThrow(/FeedbackProvider/);
  });
});
