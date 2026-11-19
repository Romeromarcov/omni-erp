/**
 * Panel de cola offline del POS — ADR-012 / CTF-008 Nivel 2.
 *
 * Muestra al cajero el ciclo completo de las ventas emitidas sin red:
 *  - Por confirmar (PENDIENTE): en cola FIFO esperando conexión / flush.
 *  - Requieren revisión (REQUIERE_REVISION): rechazadas 4xx por el servidor;
 *    no se reintentan en bucle y permiten Reintentar o Descartar.
 *  - Sincronizadas (SINCRONIZADA): mapeo folio provisional -> nota definitiva
 *    del servidor (numero_nota / id_nota_venta).
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
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import SyncIcon from '@mui/icons-material/Sync';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import ReplayIcon from '@mui/icons-material/Replay';
import type { OutboxSale } from '../../../lib/salesOutbox';

interface Props {
  open: boolean;
  items: OutboxSale[];
  online: boolean;
  flushing: boolean;
  onClose: () => void;
  onSincronizarAhora: () => void;
  onReintentar: (idempotencyKey: string) => void;
  onDescartar: (idempotencyKey: string) => void;
  onLimpiarSincronizadas: () => void;
}

function folioDe(item: OutboxSale): string {
  return item.folioProvisional || `POS-${item.idempotencyKey.slice(0, 8)}`;
}

function totalDe(item: OutboxSale): string {
  if (item.totalProvisional) {
    return item.codigoIso ? `${item.totalProvisional} ${item.codigoIso}` : item.totalProvisional;
  }
  const totales = item.payload.totales_cliente;
  if (totales && typeof totales === 'object' && 'total' in totales) {
    const val = (totales as { total?: unknown }).total;
    if (typeof val === 'string' && val) {
      return item.codigoIso ? `${val} ${item.codigoIso}` : val;
    }
  }
  return '—';
}

function fechaLocalDe(item: OutboxSale): string {
  const raw = item.payload.fecha_local;
  const date = typeof raw === 'string' ? new Date(raw) : new Date(item.createdAt);
  if (Number.isNaN(date.getTime())) return String(raw ?? item.createdAt);
  return date.toLocaleString();
}

export default function PosColaOfflinePanel({
  open,
  items,
  online,
  flushing,
  onClose,
  onSincronizarAhora,
  onReintentar,
  onDescartar,
  onLimpiarSincronizadas,
}: Props) {
  const pendientes = items.filter((i) => (i.estado ?? 'PENDIENTE') === 'PENDIENTE');
  const revision = items.filter((i) => i.estado === 'REQUIERE_REVISION');
  const sincronizadas = items.filter((i) => i.estado === 'SINCRONIZADA');

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Cola de ventas offline</DialogTitle>
      <DialogContent data-testid="pos-cola-panel">
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
            <Chip
              size="small"
              color={online ? 'success' : 'warning'}
              variant="outlined"
              label={online ? 'Conexión disponible' : 'Sin conexión'}
              data-testid="pos-cola-estado-red"
            />
            <Button
              size="small"
              variant="contained"
              startIcon={<SyncIcon />}
              disabled={!online || flushing || pendientes.length === 0}
              onClick={onSincronizarAhora}
              data-testid="pos-cola-sincronizar"
            >
              {flushing ? 'Sincronizando…' : 'Sincronizar ahora'}
            </Button>
          </Stack>

          {items.length === 0 && (
            <Typography color="text.secondary" data-testid="pos-cola-vacia">
              No hay ventas en la cola offline.
            </Typography>
          )}

          {pendientes.length > 0 && (
            <Box data-testid="pos-cola-seccion-pendientes">
              <Typography variant="subtitle2" gutterBottom>
                Por confirmar ({pendientes.length})
              </Typography>
              <List dense disablePadding>
                {pendientes.map((item) => (
                  <ListItem
                    key={item.idempotencyKey}
                    disableGutters
                    data-testid={`pos-cola-pendiente-${item.idempotencyKey}`}
                    secondaryAction={<Chip size="small" color="warning" label="Por confirmar" />}
                  >
                    <ListItemText
                      primary={`${folioDe(item)} — ${totalDe(item)}`}
                      secondary={`Fecha local: ${fechaLocalDe(item)}`}
                    />
                  </ListItem>
                ))}
              </List>
            </Box>
          )}

          {revision.length > 0 && (
            <>
              {pendientes.length > 0 && <Divider />}
              <Box data-testid="pos-cola-seccion-revision">
                <Typography variant="subtitle2" color="error" gutterBottom>
                  Requieren revisión ({revision.length})
                </Typography>
                <Stack spacing={1.5}>
                  {revision.map((item) => (
                    <Alert
                      key={item.idempotencyKey}
                      severity="error"
                      data-testid={`pos-cola-revision-${item.idempotencyKey}`}
                      action={
                        <Stack direction="row" spacing={0.5}>
                          <Button
                            size="small"
                            color="inherit"
                            startIcon={<ReplayIcon />}
                            disabled={flushing}
                            onClick={() => onReintentar(item.idempotencyKey)}
                            data-testid={`pos-cola-reintentar-${item.idempotencyKey}`}
                          >
                            Reintentar
                          </Button>
                          <Button
                            size="small"
                            color="inherit"
                            startIcon={<DeleteOutlineIcon />}
                            disabled={flushing}
                            onClick={() => onDescartar(item.idempotencyKey)}
                            data-testid={`pos-cola-descartar-${item.idempotencyKey}`}
                          >
                            Descartar
                          </Button>
                        </Stack>
                      }
                    >
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                        {folioDe(item)} — {totalDe(item)}
                      </Typography>
                      <Typography variant="body2">
                        {item.errorMensaje || 'Error de validación en el servidor.'}
                      </Typography>
                      {(item.errorCodigo || item.errorStatus) && (
                        <Typography variant="caption" color="text.secondary">
                          {item.errorCodigo ? `Código: ${item.errorCodigo}` : ''}
                          {item.errorCodigo && item.errorStatus ? ' · ' : ''}
                          {item.errorStatus ? `HTTP ${item.errorStatus}` : ''}
                        </Typography>
                      )}
                    </Alert>
                  ))}
                </Stack>
              </Box>
            </>
          )}

          {sincronizadas.length > 0 && (
            <>
              {(pendientes.length > 0 || revision.length > 0) && <Divider />}
              <Box data-testid="pos-cola-seccion-sincronizadas">
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
                  <Typography variant="subtitle2" color="success.main">
                    Sincronizadas ({sincronizadas.length})
                  </Typography>
                  <Button
                    size="small"
                    disabled={flushing}
                    onClick={onLimpiarSincronizadas}
                    data-testid="pos-cola-limpiar-historial"
                  >
                    Limpiar historial
                  </Button>
                </Stack>
                <List dense disablePadding>
                  {sincronizadas.map((item) => (
                    <ListItem
                      key={item.idempotencyKey}
                      disableGutters
                      data-testid={`pos-cola-sincronizada-${item.idempotencyKey}`}
                      secondaryAction={
                        item.alertaStockNegativo ? (
                          <Chip size="small" color="warning" variant="outlined" label="Stock negativo" />
                        ) : (
                          <Chip size="small" color="success" variant="outlined" label="Confirmada" />
                        )
                      }
                    >
                      <ListItemText
                        primary={`${folioDe(item)} → ${item.numeroNota ?? item.idNotaVenta ?? 'Confirmada'}`}
                        secondary={
                          item.idNotaVenta
                            ? `Nota servidor: ${item.idNotaVenta}`
                            : `Total provisional: ${totalDe(item)}`
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="pos-cola-cerrar">
          Cerrar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
