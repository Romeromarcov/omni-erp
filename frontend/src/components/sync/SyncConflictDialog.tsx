/**
 * Diálogo de resolución de conflictos offline (`409 CONFLICTO_VERSION`) — CTF-008 Nivel 2.
 *
 * Muestra para cada mutación en conflicto una tabla comparativa campo por campo
 * entre la edición local del usuario y la versión actual del servidor, permitiendo:
 *   - Reintentar usando el `fecha_actualizacion` actual del servidor (`CONFLICTO_VERSION`).
 *   - Descartar el cambio local aceptando la versión del servidor.
 */
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import ReplayIcon from '@mui/icons-material/Replay';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import type { SyncConflictItem } from '../../lib/syncConflictQueue';

interface Props {
  open: boolean;
  conflicts: SyncConflictItem[];
  retryingKey?: string | null;
  errorMessage?: string | null;
  onClose: () => void;
  onRetryWithServerCursor: (item: SyncConflictItem) => void;
  onAcceptServerVersion: (conflictKey: string) => void;
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—';
  if (typeof val === 'boolean') return val ? 'Sí' : 'No';
  return String(val);
}

export default function SyncConflictDialog({
  open,
  conflicts,
  retryingKey = null,
  errorMessage = null,
  onClose,
  onRetryWithServerCursor,
  onAcceptServerVersion,
}: Props) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Conflictos de sincronización offline</DialogTitle>
      <DialogContent data-testid="sync-conflict-dialog">
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          {errorMessage && (
            <Alert severity="error" data-testid="sync-conflict-error">
              {errorMessage}
            </Alert>
          )}

          {conflicts.length === 0 ? (
            <Typography color="text.secondary" data-testid="sync-conflict-empty">
              No hay conflictos pendientes por resolver.
            </Typography>
          ) : (
            conflicts.map((item, idx) => {
              const serverEntries = new Map<string, unknown>(Object.entries(item.serverRecord));
              const localChanges = Object.entries(item.mutation.cambios);
              const isRetrying = retryingKey === item.conflictKey;

              return (
                <Box key={item.conflictKey} data-testid={`sync-conflict-item-${item.conflictKey}`}>
                  {idx > 0 && <Divider sx={{ mb: 2 }} />}
                  <Alert severity="warning" sx={{ mb: 1.5 }}>
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      justifyContent="space-between"
                      alignItems={{ sm: 'center' }}
                      spacing={1}
                    >
                      <Box>
                        <Typography variant="subtitle2">
                          {item.mutation.entity} · {item.mutation.id}
                        </Typography>
                        <Typography variant="body2">{item.message}</Typography>
                      </Box>
                      <Chip size="small" color="warning" label="CONFLICTO_VERSION (409)" />
                    </Stack>
                  </Alert>

                  <Table size="small" aria-label={`Comparación conflicto ${item.conflictKey}`}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Campo</TableCell>
                        <TableCell>Tu versión local</TableCell>
                        <TableCell>Versión del servidor</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {localChanges.map(([campo, valorLocal]) => (
                        <TableRow key={campo}>
                          <TableCell sx={{ fontWeight: 'bold' }}>{campo}</TableCell>
                          <TableCell data-testid={`conflict-local-${campo}`}>
                            {formatValue(valorLocal)}
                          </TableCell>
                          <TableCell data-testid={`conflict-server-${campo}`}>
                            {formatValue(serverEntries.get(campo))}
                          </TableCell>
                        </TableRow>
                      ))}
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold' }}>fecha_actualizacion</TableCell>
                        <TableCell>{item.mutation.expected_fecha_actualizacion}</TableCell>
                        <TableCell>{item.serverRecord.fecha_actualizacion}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>

                  <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 1.5 }}>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<CheckCircleOutlineIcon />}
                      disabled={isRetrying}
                      onClick={() => onAcceptServerVersion(item.conflictKey)}
                      data-testid={`sync-conflict-discard-${item.conflictKey}`}
                    >
                      Aceptar servidor / Descartar
                    </Button>
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<ReplayIcon />}
                      disabled={isRetrying}
                      onClick={() => onRetryWithServerCursor(item)}
                      data-testid={`sync-conflict-retry-${item.conflictKey}`}
                    >
                      {isRetrying ? 'Reintentando…' : 'Reintentar con versión actual'}
                    </Button>
                  </Stack>
                </Box>
              );
            })
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="sync-conflict-close">
          Cerrar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
