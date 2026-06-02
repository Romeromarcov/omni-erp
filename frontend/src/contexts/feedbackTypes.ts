import { createContext, useContext } from 'react';
import type { AlertColor } from '@mui/material/Alert';

/**
 * FE-NEW-2: tipos, contexto y hooks del provider de feedback de UI.
 *
 * Vive en un módulo sin JSX para que el componente `FeedbackProvider`
 * (en `FeedbackContext.tsx`) cumpla la regla `react-refresh/only-export-components`
 * (un archivo de componentes solo debe exportar componentes).
 */

export type SnackbarSeverity = AlertColor;

export interface SnackbarApi {
  notify: (message: string, severity?: SnackbarSeverity) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  warning: (message: string) => void;
}

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  /** Marca la acción como destructiva (botón en color "error"). */
  destructive?: boolean;
}

export type ConfirmFn = (options: ConfirmOptions | string) => Promise<boolean>;

export interface FeedbackContextValue {
  snackbar: SnackbarApi;
  confirm: ConfirmFn;
}

export const FeedbackContext = createContext<FeedbackContextValue | null>(null);

function useFeedback(): FeedbackContextValue {
  const ctx = useContext(FeedbackContext);
  if (!ctx) {
    throw new Error('useFeedback debe usarse dentro de <FeedbackProvider>');
  }
  return ctx;
}

export function useSnackbar(): SnackbarApi {
  return useFeedback().snackbar;
}

export function useConfirm(): ConfirmFn {
  return useFeedback().confirm;
}
