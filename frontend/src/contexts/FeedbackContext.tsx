import React, { useCallback, useMemo, useRef, useState } from 'react';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import Button from '@mui/material/Button';
import {
  FeedbackContext,
  type ConfirmFn,
  type ConfirmOptions,
  type FeedbackContextValue,
  type SnackbarApi,
  type SnackbarSeverity,
} from './feedbackTypes';

/**
 * FE-NEW-2: Provider global de feedback de UI que reemplaza los `alert()` y
 * `confirm()` nativos del navegador.
 *
 *  - `useSnackbar()` (en `feedbackTypes.ts`) muestra mensajes no bloqueantes con
 *    `<Snackbar>` + `<Alert>` (`notify`, `success`, `error`, `info`, `warning`).
 *  - `useConfirm()` abre un `<Dialog>` MUI de confirmación que resuelve a
 *    `true`/`false`, pensado para acciones destructivas.
 */

interface SnackbarState {
  open: boolean;
  message: string;
  severity: SnackbarSeverity;
}

interface ConfirmState extends ConfirmOptions {
  open: boolean;
}

const DEFAULT_CONFIRM: ConfirmState = {
  open: false,
  title: 'Confirmar',
  message: '',
  confirmText: 'Confirmar',
  cancelText: 'Cancelar',
  destructive: false,
};

export const FeedbackProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [snack, setSnack] = useState<SnackbarState>({
    open: false,
    message: '',
    severity: 'info',
  });

  const [confirmState, setConfirmState] = useState<ConfirmState>(DEFAULT_CONFIRM);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const notify = useCallback((message: string, severity: SnackbarSeverity = 'info') => {
    setSnack({ open: true, message, severity });
  }, []);

  const snackbar = useMemo<SnackbarApi>(
    () => ({
      notify,
      success: (message: string) => notify(message, 'success'),
      error: (message: string) => notify(message, 'error'),
      info: (message: string) => notify(message, 'info'),
      warning: (message: string) => notify(message, 'warning'),
    }),
    [notify],
  );

  const confirm = useCallback<ConfirmFn>((options) => {
    const opts: ConfirmOptions = typeof options === 'string' ? { message: options } : options;
    setConfirmState({ ...DEFAULT_CONFIRM, ...opts, open: true });
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const closeConfirm = useCallback((result: boolean) => {
    setConfirmState((prev) => ({ ...prev, open: false }));
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
  }, []);

  const handleSnackClose = useCallback((_e?: unknown, reason?: string) => {
    if (reason === 'clickaway') return;
    setSnack((prev) => ({ ...prev, open: false }));
  }, []);

  const value = useMemo<FeedbackContextValue>(() => ({ snackbar, confirm }), [snackbar, confirm]);

  return (
    <FeedbackContext.Provider value={value}>
      {children}
      <Snackbar
        open={snack.open}
        autoHideDuration={5000}
        onClose={handleSnackClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => handleSnackClose()}
          severity={snack.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snack.message}
        </Alert>
      </Snackbar>
      <Dialog open={confirmState.open} onClose={() => closeConfirm(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{confirmState.title}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ whiteSpace: 'pre-line' }}>
            {confirmState.message}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => closeConfirm(false)} color="inherit">
            {confirmState.cancelText}
          </Button>
          <Button
            onClick={() => closeConfirm(true)}
            color={confirmState.destructive ? 'error' : 'primary'}
            variant="contained"
            autoFocus
          >
            {confirmState.confirmText}
          </Button>
        </DialogActions>
      </Dialog>
    </FeedbackContext.Provider>
  );
};
